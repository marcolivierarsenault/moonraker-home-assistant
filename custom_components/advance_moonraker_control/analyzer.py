"""Server-side telemetry analyzer for Moonraker printers.

Derives health findings, flow, bed-mesh drift, energy, and per-print history
from the coordinator's already-subscribed status objects so detection keeps
working without any browser panel open. All state is per config entry and
persisted through Home Assistant's Store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import statistics
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    CONF_OPTION_AI_TASK_ENTITY,
    CONF_OPTION_AMBIENT_SENSOR,
    CONF_OPTION_ENERGY_RATE,
    CONF_OPTION_MAX_FLOW,
    CONF_OPTION_NOTIFY_SERVICE,
    CONF_OPTION_POWER_OFF_DELAY,
    CONF_OPTION_POWER_OFF_MAX_TEMP,
    CONF_OPTION_POWER_SENSOR,
    CONF_OPTION_POWER_SWITCH,
    CONF_OPTION_VISION_CAMERA,
    DEFAULT_MAX_FLOW_MM3,
    DEFAULT_POWER_OFF_DELAY_MIN,
    DEFAULT_POWER_OFF_MAX_TEMP,
    DOMAIN,
    SIGNAL_PRINT_EVENT,
)

if TYPE_CHECKING:
    from . import MoonrakerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_SUFFIX = "analyzer"
SAVE_DEBOUNCE_SECONDS = 15
PRINT_HISTORY_LIMIT = 50
THERMAL_SAMPLE_LIMIT = 120
RETRANSMIT_SAMPLE_LIMIT = 120
MESH_RMS_DUE_MM = 0.10
MESH_HISTORY_LIMIT = 12
MESH_TILT_SHIFT_WARN = 0.02
LAYER_HISTORY_LIMIT = 240
LAYER_PERIOD_MIN_LAYERS = 12
LAYER_PERIOD_MIN_CORR = 0.55
FIRST_LAYER_Z_MAX_MM = 0.5
FIRST_LAYER_BIN_MM = 10
DRIVER_TEMP_WARN_C = 60.0
DRIVER_TEMP_SHUTDOWN_C = 90.0
VOLTAGE_SAG_PCT = 8.0
HEATER_EFFICIENCY_DRIFT_PCT = 20.0
HEATER_STEADY_SECONDS = 120.0
NOZZLE_WEAR_DROP_PCT = 20.0
FILE_STATS_LIMIT = 60
FORENSIC_SAMPLE_LIMIT = 120
TWIN_HISTORY_LIMIT = 30
HIGH_SHRINK_MATERIALS = ("ABS", "ASA", "PC", "PA", "NYLON", "HIPS")
CHAMBER_WARM_MIN_C = 30.0
MESH_FRESH_DAYS = 14
MESH_MAX_DUE_MM = 0.15
MESH_RMS_WARN_MM = 0.05
MESH_MAX_WARN_MM = 0.08
FLOW_SATURATION_SECONDS = 5
STALL_CHECK_SECONDS = 30
STALL_MIN_VELOCITY_MM_S = 3.0
STALL_FILAMENT_EPSILON_MM = 0.5
FILAMENT_AREA_MM2 = math.pi * (1.75**2) / 4
HEATUP_MIN_TARGET_C = 40.0
HEATUP_TOLERANCE_C = 2.0
HEATUP_MIN_SECONDS = 5.0
HEATUP_SLOW_RATIO = 1.2
HEATUP_HISTORY_LIMIT = 5
AMBIENT_COLD_C = 18.0
VELOCITY_OVER_LIMIT_RATIO = 1.15
VELOCITY_OVER_LIMIT_SAMPLES = 3
SPOOL_SHORT_RATIO = 1.05
VISION_INTERVAL_SECONDS = 300
VISION_TASK_NAME = "moonraker print check"
CHECKPOINT_INTERVAL_SECONDS = 60
CHECKPOINT_LIMIT = 40
CHECKPOINT_KEPT_ON_RECORD = 5

_SPAGHETTI_PROMPT = (
    "Look at this 3D printer camera frame. If the print shows obvious "
    "failure signs — spaghetti plastic, detached parts, the nozzle dragging "
    "a loose object, or nothing on the bed — answer FAIL. If the print looks "
    "normal or you cannot tell, answer OK. Reply with exactly one word."
)
_FIRST_LAYER_PROMPT = (
    "Look at this 3D printer camera frame taken right after the first "
    "layer. If the first layer shows obvious adhesion gaps, bare spots, or "
    "the nozzle printing in mid-air, answer FAIL. Otherwise answer OK. "
    "Reply with exactly one word."
)
_CAPTION_PROMPT = (
    "Describe this finished 3D print in 15 words or fewer: object shape, "
    "surface quality, and any visible defects. Reply with the caption only."
)

# Approximate slicer material profiles: nozzle/bed target ranges in °C and
# whether a warm enclosure is expected.
MATERIAL_PROFILES: dict[str, dict[str, Any]] = {
    "PLA": {"nozzle": (180, 225), "bed": (0, 65), "enclosure": False},
    "PETG": {"nozzle": (220, 260), "bed": (60, 90), "enclosure": False},
    "ABS": {"nozzle": (230, 270), "bed": (90, 115), "enclosure": True},
    "ASA": {"nozzle": (230, 270), "bed": (90, 115), "enclosure": True},
    "TPU": {"nozzle": (200, 240), "bed": (30, 70), "enclosure": False},
    "PA": {"nozzle": (240, 300), "bed": (60, 100), "enclosure": True},
    "PC": {"nozzle": (260, 320), "bed": (90, 130), "enclosure": True},
}

_HEATER_GENERIC_RE = re.compile(r"^heater_generic (.+)$")
_MCU_RE = re.compile(r"^mcu")
_PRINT_STATE_EVENTS = {
    "complete": "print_completed",
    "cancelled": "print_cancelled",
    "error": "print_error",
}


def _now_ts() -> float:
    """Return the current UNIX timestamp."""
    return datetime.now(tz=timezone.utc).timestamp()


def _iso(ts: float) -> str:
    """Format a UNIX timestamp as ISO-8601."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _finite_number(value: Any) -> float | None:
    """Coerce a value to a finite float or return None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _matrix_from_mesh(mesh: dict[str, Any]) -> list[list[float]] | None:
    """Extract a numeric bed-mesh matrix from a Klipper bed_mesh object."""
    matrix = mesh.get("mesh_matrix") or mesh.get("probed_matrix")
    if not isinstance(matrix, list) or not matrix or not isinstance(matrix[0], list):
        return None
    rows: list[list[float]] = []
    for row in matrix:
        if not isinstance(row, list) or not row or len(row) != len(matrix[0]):
            return None
        converted = [_finite_number(cell) for cell in row]
        if any(cell is None for cell in converted):
            return None
        rows.append([float(cell) for cell in converted])
    return rows


def _fit_plane(matrix: list[list[float]]) -> tuple[float, float, float]:
    """Least-squares fit z = a*col + b*row + c over the mesh grid.

    A tilted tram moves every cell by a plane; fitting and removing that
    plane isolates the bed's surface shape (waviness) from frame tilt.
    Returns (a, b, c) in mm per grid index.
    """
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if not rows or not cols or rows * cols < 3:
        return (0.0, 0.0, 0.0)
    sx = sy = sxx = syy = sxy = sxz = syz = sz = 0.0
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            sx += j
            sy += i
            sxx += j * j
            syy += i * i
            sxy += i * j
            sxz += j * value
            syz += i * value
            sz += value
    n = float(rows * cols)
    # Normal equations for the 3x3 system, solved by Gaussian elimination.
    system = [
        [sxx, sxy, sx, sxz],
        [sxy, syy, sy, syz],
        [sx, sy, n, sz],
    ]
    for pivot in range(3):
        lead = max(range(pivot, 3), key=lambda r: abs(system[r][pivot]))
        system[pivot], system[lead] = system[lead], system[pivot]
        divisor = system[pivot][pivot]
        if abs(divisor) < 1e-12:
            return (0.0, 0.0, 0.0)
        system[pivot] = [term / divisor for term in system[pivot]]
        for other in range(3):
            if other == pivot:
                continue
            factor = system[other][pivot]
            system[other] = [
                term - factor * system[pivot][index]
                for index, term in enumerate(system[other])
            ]
    return (system[0][3], system[1][3], system[2][3])


def _mesh_surface_stats(matrix: list[list[float]]) -> dict[str, Any]:
    """Decompose a mesh into tilt plane, corner offsets, and residual RMS."""
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    a, b, c = _fit_plane(matrix)
    residuals = [
        [value - (a * j + b * i + c) for j, value in enumerate(row)]
        for i, row in enumerate(matrix)
    ]
    squares = sum(residual * residual for row in residuals for residual in row)
    residual_rms = math.sqrt(squares / max(1, rows * cols))
    corner_points = [(0, 0), (0, cols - 1), (rows - 1, 0), (rows - 1, cols - 1)]
    corner_heights = [a * j + b * i + c for i, j in corner_points]
    lowest = min(corner_heights)
    corners = [round(height - lowest, 4) for height in corner_heights]
    fingerprint = repr([[round(value, 4) for value in row] for row in matrix])
    return {
        "tilt_a": a,
        "tilt_b": b,
        "intercept": c,
        "corners": corners,
        "residuals": residuals,
        "residual_rms": residual_rms,
        "fp": fingerprint,
    }


def _drift_stats(matrix: list[list[float]], baseline: list[list[float]]) -> dict:
    """Compute RMS/max drift between two same-shaped matrices."""
    if len(matrix) != len(baseline) or any(
        len(matrix[index]) != len(baseline[index]) for index in range(len(matrix))
    ):
        return {"rms": 0.0, "max": 0.0, "cells": []}
    squares = 0.0
    count = 0
    worst = 0.0
    cells: list[float] = []
    for row_index, row in enumerate(matrix):
        for cell_index, value in enumerate(row):
            delta = value - baseline[row_index][cell_index]
            squares += delta * delta
            count += 1
            worst = max(worst, abs(delta))
            cells.append(delta)
    return {
        "rms": math.sqrt(squares / count) if count else 0.0,
        "max": worst,
        "cells": cells,
    }


class MoonrakerAnalyzer:
    """Analyze coordinator status into metrics, findings, and history."""

    def __init__(self, hass, coordinator: MoonrakerDataUpdateCoordinator) -> None:
        """Initialize the analyzer bound to one config entry."""
        self.hass = hass
        self.coordinator = coordinator
        options = coordinator.config_entry.options
        self.max_flow_mm3 = (
            _finite_number(options.get(CONF_OPTION_MAX_FLOW)) or DEFAULT_MAX_FLOW_MM3
        )
        self.energy_rate = _finite_number(options.get(CONF_OPTION_ENERGY_RATE)) or 0.0
        self.power_sensor = str(options.get(CONF_OPTION_POWER_SENSOR) or "")
        self.notify_service = str(options.get(CONF_OPTION_NOTIFY_SERVICE) or "")
        self.power_switch = str(options.get(CONF_OPTION_POWER_SWITCH) or "")
        self.power_off_delay = (
            _finite_number(options.get(CONF_OPTION_POWER_OFF_DELAY))
            or DEFAULT_POWER_OFF_DELAY_MIN
        )
        self.power_off_max_temp = (
            _finite_number(options.get(CONF_OPTION_POWER_OFF_MAX_TEMP))
            or DEFAULT_POWER_OFF_MAX_TEMP
        )
        self.ambient_sensor = str(options.get(CONF_OPTION_AMBIENT_SENSOR) or "")
        self.ai_task_entity = str(options.get(CONF_OPTION_AI_TASK_ENTITY) or "")
        self.vision_camera = str(options.get(CONF_OPTION_VISION_CAMERA) or "")
        self._last_vision_check: float | None = None
        self._vision_task: asyncio.Task | None = None
        self._vision_alerts: list[dict[str, str]] = []
        self._first_layer_checked_for: str | None = None
        self.checkpoints: deque[dict[str, Any]] = deque(maxlen=CHECKPOINT_LIMIT)
        self._last_checkpoint_at: float | None = None
        self._heatup_active: dict[str, dict[str, float]] = {}
        self._heatup_history: dict[str, list[float]] = {}
        self._over_limit_samples = 0
        self.thermal_history: dict[str, deque[dict[str, float]]] = {}
        self.retransmit_history: deque[dict[str, float]] = deque(
            maxlen=RETRANSMIT_SAMPLE_LIMIT
        )
        self._mesh_baseline: dict[str, Any] | None = None
        self.mesh_history: list[dict[str, Any]] = []
        self._layer_boundary: dict[str, float] | None = None
        self._layer_times: deque[dict[str, float]] = deque(maxlen=LAYER_HISTORY_LIMIT)
        self._print_layer_durations: list[float] = []
        self._prev_position: list[float] | None = None
        self._prev_filament_used: float | None = None
        self._prev_sample_at: float | None = None
        self._prev_ext_velocity: float = 0.0
        self._last_extrusion_at: float | None = None
        self._stutter_events: deque[float] = deque(maxlen=240)
        self.extruder_skips = 0
        self._first_layer_bins: dict[str, float] = {}
        self._steady_since: dict[str, float] = {}
        self._power_ratio_at: dict[str, float] = {}
        self.heater_power_history: dict[str, list[float]] = {}
        self.flow_peaks: dict[str, list[float]] = {}
        self._print_peak_flow = 0.0
        self._tmc_history: deque[tuple[float, float]] = deque(maxlen=60)
        self._voltage_history: dict[str, deque[tuple[float, float]]] = {}
        self._voltage_baseline: dict[str, float] = {}
        self.config_hash: str | None = None
        self.config_changed_at: str | None = None
        self.file_stats: dict[str, dict[str, Any]] = {}
        self.golden_runs: dict[str, dict[str, Any]] = {}
        self.eta_factors: dict[str, float] = {}
        self._telemetry_ring: deque[dict[str, Any]] = deque(
            maxlen=FORENSIC_SAMPLE_LIMIT
        )
        self._ring_last_at: float | None = None
        self._print_start_ambient: float | None = None
        self._oee_printing_s = 0.0
        self._oee_window_s = 0.0
        self._oee_last_at: float | None = None
        self._print_flow_sum = 0.0
        self._print_flow_count = 0
        self._print_temp_samples: list[float] = []
        self._flow_saturated_since: float | None = None
        self._stall_window: dict[str, float] | None = None
        self._prev_print_state: str | None = None
        self._print_started_at: float | None = None
        self._print_faults: set[str] = set()
        self.energy_session: dict[str, Any] = {
            "filename": "",
            "kwh": 0.0,
            "last_at": None,
        }
        self.total_kwh: float = 0.0
        self.print_history: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] = {
            "volumetric_flow_mm3": None,
            "flow_headroom_pct": None,
            "mesh_rms_drift_mm": None,
            "mesh_max_drift_mm": None,
            "mesh_status": "unknown",
            "print_energy_kwh": None,
            "print_cost": None,
            "total_kwh": 0.0,
            "retransmit_total": 0,
            "retransmit_trend": "stable",
        }
        self.findings: list[dict[str, str]] = []
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{coordinator.config_entry.entry_id}.{STORAGE_KEY_SUFFIX}",
        )
        self._store_loaded = False
        self._store_dirty = False
        self._save_unsub: Callable[[], None] | None = None
        self._power_off_unsub: Callable[[], None] | None = None
        self._power_off_armed = False
        from .printcast import MoonrakerPrintcast

        self.printcast = MoonrakerPrintcast(self, self._mark_dirty)

    async def async_load(self) -> None:
        """Restore persisted baselines, history, and energy totals."""
        try:
            stored = await self._store.async_load()
        except Exception:  # noqa: BLE001 - a corrupt store must not break setup
            _LOGGER.warning(
                "Could not load analyzer store for %s", self.coordinator.api_device_name
            )
            stored = None
        if isinstance(stored, dict):
            baseline = stored.get("mesh_baseline")
            if isinstance(baseline, dict) and isinstance(baseline.get("matrix"), list):
                self._mesh_baseline = baseline
            mesh_history = stored.get("mesh_history")
            if isinstance(mesh_history, list):
                self.mesh_history = [
                    record for record in mesh_history if isinstance(record, dict)
                ][-MESH_HISTORY_LIMIT:]
            history = stored.get("print_history")
            if isinstance(history, list):
                self.print_history = [
                    record for record in history if isinstance(record, dict)
                ][-PRINT_HISTORY_LIMIT:]
            self.total_kwh = _finite_number(stored.get("total_kwh")) or 0.0
            checkpoints = stored.get("checkpoints")
            if isinstance(checkpoints, list):
                self.checkpoints = deque(
                    [point for point in checkpoints if isinstance(point, dict)],
                    maxlen=CHECKPOINT_LIMIT,
                )
            heatup = stored.get("heatup_history")
            if isinstance(heatup, dict):
                self._heatup_history = {
                    str(label): [
                        value for value in samples if _finite_number(value) is not None
                    ][-HEATUP_HISTORY_LIMIT:]
                    for label, samples in heatup.items()
                    if isinstance(samples, list)
                }
            power_history = stored.get("heater_power_history")
            if isinstance(power_history, dict):
                self.heater_power_history = {
                    str(label): [
                        value for value in samples if _finite_number(value) is not None
                    ][-20:]
                    for label, samples in power_history.items()
                    if isinstance(samples, list)
                }
            flow_peaks = stored.get("flow_peaks")
            if isinstance(flow_peaks, dict):
                self.flow_peaks = {
                    str(material): [
                        value for value in peaks if _finite_number(value) is not None
                    ][-10:]
                    for material, peaks in flow_peaks.items()
                    if isinstance(peaks, list)
                }
            file_stats = stored.get("file_stats")
            if isinstance(file_stats, dict):
                self.file_stats = {
                    str(name): dict(record)
                    for name, record in list(file_stats.items())[-FILE_STATS_LIMIT:]
                    if isinstance(record, dict)
                }
            golden = stored.get("golden_runs")
            if isinstance(golden, dict):
                self.golden_runs = {
                    str(name): dict(record)
                    for name, record in list(golden.items())[-TWIN_HISTORY_LIMIT:]
                    if isinstance(record, dict)
                }
            eta = stored.get("eta_factors")
            if isinstance(eta, dict):
                self.eta_factors = {
                    str(key): value
                    for key, value in eta.items()
                    if _finite_number(value) is not None
                }
            config_hash = stored.get("config_hash")
            if isinstance(config_hash, str):
                self.config_hash = config_hash
            config_changed = stored.get("config_changed_at")
            if isinstance(config_changed, str):
                self.config_changed_at = config_changed
            self._oee_printing_s = _finite_number(stored.get("oee_printing_s")) or 0.0
            self._oee_window_s = _finite_number(stored.get("oee_window_s")) or 0.0
            self.printcast.load_state(stored)
        self.metrics["total_kwh"] = round(self.total_kwh, 4)
        self._store_loaded = True
        if self._store_dirty:
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        """Schedule a debounced store write."""
        self._store_dirty = True
        if self._save_unsub is not None or not self._store_loaded:
            return
        self._save_unsub = async_call_later(
            self.hass, timedelta(seconds=SAVE_DEBOUNCE_SECONDS), self._async_save
        )

    async def _async_save(self, _now: Any = None) -> None:
        """Persist analyzer state to the Store."""
        self._save_unsub = None
        if not self._store_dirty:
            return
        self._store_dirty = False
        try:
            await self._store.async_save(
                {
                    "mesh_baseline": self._mesh_baseline,
                    "mesh_history": self.mesh_history[-MESH_HISTORY_LIMIT:],
                    "print_history": self.print_history[-PRINT_HISTORY_LIMIT:],
                    "total_kwh": round(self.total_kwh, 6),
                    "heatup_history": self._heatup_history,
                    "heater_power_history": self.heater_power_history,
                    "flow_peaks": self.flow_peaks,
                    "file_stats": self.file_stats,
                    "golden_runs": self.golden_runs,
                    "eta_factors": self.eta_factors,
                    "config_hash": self.config_hash,
                    "config_changed_at": self.config_changed_at,
                    "checkpoints": list(self.checkpoints),
                    "oee_printing_s": self._oee_printing_s,
                    "oee_window_s": self._oee_window_s,
                    **self.printcast.dump_state(),
                }
            )
        except Exception:  # noqa: BLE001 - persistence failure is non-fatal
            _LOGGER.warning("Could not save analyzer store")

    async def async_shutdown(self) -> None:
        """Cancel the debounce timer and persist pending state on unload."""
        if self._save_unsub is not None:
            self._save_unsub()
            self._save_unsub = None
        if self._power_off_unsub is not None:
            self._power_off_unsub()
            self._power_off_unsub = None
            self._power_off_armed = False
        if self._vision_task is not None and not self._vision_task.done():
            self._vision_task.cancel()
            self._vision_task = None
        if self._store_dirty:
            await self._async_save()

    # -- subscriptions ------------------------------------------------------

    def required_subscriptions(self, object_names: list[str]) -> list[tuple[str, str]]:
        """Return extra printer objects the analyzer needs subscribed."""
        subscriptions: list[tuple[str, str]] = [
            ("motion_report", "live_extruder_velocity"),
        ]
        if "exclude_object" in object_names:
            subscriptions.append(("exclude_object", None))
        for name in object_names:
            if _HEATER_GENERIC_RE.match(name):
                subscriptions.append((name, "temperature"))
                subscriptions.append((name, "power"))
            if name in ("extruder", "heater_bed"):
                subscriptions.append((name, "power"))
        return subscriptions

    # -- analysis entry point ------------------------------------------------

    def analyze(self, status: dict[str, Any], now: float | None = None) -> None:
        """Refresh metrics and findings from the latest status payload."""
        if now is None:
            now = _now_ts()
        if not isinstance(status, dict):
            status = {}
        # Sections must be objects; a malformed payload yields empty sections.
        status = {
            key: value if isinstance(value, dict) else {}
            for key, value in status.items()
        }
        findings: list[dict[str, str]] = []
        findings.extend(self._analyze_thermal(status, now))
        findings.extend(self._analyze_flow(status, now))
        findings.extend(self._analyze_retransmits(status, now))
        findings.extend(self._analyze_extrusion_stall(status, now))
        findings.extend(self._analyze_heatup(status, now))
        findings.extend(self._analyze_spool())
        findings.extend(self._analyze_material(status))
        findings.extend(self._analyze_mesh(status, now))
        findings.extend(self._analyze_kinematics(status))
        findings.extend(self._analyze_layers(status, now))
        findings.extend(self._analyze_stutter(status, now))
        findings.extend(self._analyze_drivers(status, now))
        findings.extend(self._analyze_voltages(status))
        findings.extend(self._analyze_thermistor_health(status, now))
        self._track_first_layer_flow(status)
        self._track_twin(status, now)
        self._record_telemetry(status, now)
        self._update_preflight(status, now)
        self._update_oee(status, now)
        self._track_energy(status, now)
        self._track_print_state(status, now, findings)
        self._track_checkpoints(status, now)
        self._maybe_schedule_vision(status, now)
        findings.extend(self._analyze_queue_plan())
        findings.extend(self._vision_alerts)
        findings.extend(self.printcast.analyze(status, now, findings))
        self.findings = findings
        self._sync_repairs()

    # -- thermal sentinel ----------------------------------------------------

    def _heater_objects(self, status: dict[str, Any]) -> list[tuple[str, dict]]:
        heaters: list[tuple[str, dict]] = []
        extruder = status.get("extruder")
        if isinstance(extruder, dict):
            heaters.append(("extruder", extruder))
        bed = status.get("heater_bed")
        if isinstance(bed, dict):
            heaters.append(("heater_bed", bed))
        for name, value in status.items():
            match = _HEATER_GENERIC_RE.match(name)
            if match and isinstance(value, dict):
                heaters.append((name, value))
        return heaters

    def _analyze_thermal(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        for label, heater in self._heater_objects(status):
            temperature = _finite_number(heater.get("temperature"))
            duty = _finite_number(heater.get("power"))
            target = _finite_number(heater.get("target"))
            if temperature is None or duty is None:
                continue
            history = self.thermal_history.setdefault(
                label, deque(maxlen=THERMAL_SAMPLE_LIMIT)
            )
            history.append({"at": now, "t": temperature, "p": duty})
            if len(history) < 20 or target is None or target <= 5:
                continue
            recent = list(history)[-15:]
            mean_duty = sum(sample["p"] for sample in recent) / len(recent)
            slope = recent[-1]["t"] - recent[0]["t"]
            if mean_duty > 0.95 and slope < -1:
                findings.append(
                    {
                        "severity": "bad",
                        "label": f"{label} saturated",
                        "detail": "100% duty while temperature falls",
                    }
                )
                continue
            window = list(history)[-60:]
            temps = [sample["t"] for sample in window]
            amplitude = max(temps) - min(temps)
            crossings = sum(
                1
                for index in range(1, len(temps))
                if (temps[index - 1] - target) * (temps[index] - target) < 0
            )
            if amplitude > 3 and crossings >= 6:
                findings.append(
                    {
                        "severity": "warn",
                        "label": f"{label} pid oscillation",
                        "detail": f"±{amplitude / 2:.1f}°C around target",
                    }
                )
        return findings

    # -- volumetric flow ------------------------------------------------------

    def _analyze_flow(self, status: dict[str, Any], now: float) -> list[dict[str, str]]:
        motion = status.get("motion_report") or {}
        velocity = _finite_number(motion.get("live_extruder_velocity"))
        mm3 = velocity * FILAMENT_AREA_MM2 if velocity and velocity > 0 else 0.0
        self.metrics["volumetric_flow_mm3"] = round(mm3, 2)
        ratio = mm3 / self.max_flow_mm3 if self.max_flow_mm3 > 0 else 0.0
        self.metrics["flow_headroom_pct"] = round(max(0.0, 1.0 - ratio) * 100, 1)
        if mm3 > 0 and ratio >= 0.95:
            if self._flow_saturated_since is None:
                self._flow_saturated_since = now
            elif now - self._flow_saturated_since >= FLOW_SATURATION_SECONDS:
                return [
                    {
                        "severity": "warn",
                        "label": "flow saturated",
                        "detail": f"{mm3:.1f} mm³/s at melt limit",
                    }
                ]
        else:
            self._flow_saturated_since = None
        return []

    # -- mcu retransmits -------------------------------------------------------

    def _analyze_retransmits(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        total = 0
        for name, value in status.items():
            if not _MCU_RE.match(name) or not isinstance(value, dict):
                continue
            stats = value.get("last_stats") or {}
            total += int(_finite_number(stats.get("bytes_retransmit")) or 0)
            total += int(_finite_number(stats.get("bytes_invalid")) or 0)
        self.retransmit_history.append({"at": now, "total": total})
        trend = "stable"
        first = self.retransmit_history[0]
        if len(self.retransmit_history) >= 3 and (
            total > first["total"] and now - first["at"] < 600
        ):
            trend = "rising"
        self.metrics["retransmit_total"] = total
        self.metrics["retransmit_trend"] = trend
        if total:
            return [
                {
                    "severity": "warn" if trend == "rising" else "ok",
                    "label": "mcu retransmit",
                    "detail": f"{total} bytes / {trend}",
                }
            ]
        return []

    # -- ghost-print / extrusion stall ----------------------------------------

    def _analyze_extrusion_stall(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        print_stats = status.get("print_stats") or {}
        if print_stats.get("state") != "printing":
            self._stall_window = None
            return []
        motion = status.get("motion_report") or {}
        velocity = _finite_number(motion.get("live_velocity")) or 0.0
        extruder_velocity = _finite_number(motion.get("live_extruder_velocity"))
        filament = _finite_number(print_stats.get("filament_used")) or 0.0
        moving = velocity >= STALL_MIN_VELOCITY_MM_S
        extruding = extruder_velocity is None or abs(extruder_velocity) > 0.01
        if not moving or extruding:
            self._stall_window = None
            return []
        if self._stall_window is None:
            self._stall_window = {"at": now, "filament": filament}
            return []
        elapsed = now - self._stall_window["at"]
        if elapsed < STALL_CHECK_SECONDS:
            return []
        advanced = filament - self._stall_window["filament"]
        if advanced >= STALL_FILAMENT_EPSILON_MM:
            self._stall_window = {"at": now, "filament": filament}
            return []
        finding = {
            "severity": "bad",
            "label": "extrusion stall",
            "detail": "moving without extruding for "
            f"{int(elapsed)}s — possible air printing",
        }
        self._stall_window = {"at": now, "filament": filament}
        return [finding]

    # -- heat-up learning --------------------------------------------------------

    def _analyze_heatup(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        still_heating: set[str] = set()
        for label, heater in self._heater_objects(status):
            temp = _finite_number(heater.get("temperature"))
            target = _finite_number(heater.get("target"))
            if temp is None or target is None or target < HEATUP_MIN_TARGET_C:
                continue
            entry = self._heatup_active.get(label)
            if temp < target - HEATUP_TOLERANCE_C:
                if entry is None or abs(entry["target"] - target) > 1:
                    self._heatup_active[label] = {"start": now, "target": target}
                still_heating.add(label)
                continue
            if entry is None:
                continue
            duration = now - entry["start"]
            del self._heatup_active[label]
            if duration < HEATUP_MIN_SECONDS:
                continue
            baseline = self._heatup_history.setdefault(label, [])
            if len(baseline) >= 3:
                typical = statistics.median(baseline)
                if duration > typical * HEATUP_SLOW_RATIO:
                    findings.append(
                        {
                            "severity": "warn",
                            "label": "slow heat-up",
                            "detail": (
                                f"{label} took {int(duration)}s to reach "
                                f"{target:.0f}°C (typically {int(typical)}s) — "
                                "check the heater cartridge and thermistor"
                            ),
                        }
                    )
            baseline.append(duration)
            del baseline[:-HEATUP_HISTORY_LIMIT]
            self._mark_dirty()
        for label in list(self._heatup_active):
            if label not in still_heating:
                del self._heatup_active[label]
        return findings

    # -- spool cross-check ---------------------------------------------------------

    def _spool_remaining_mm(self, spool: dict[str, Any]) -> float | None:
        remaining = _finite_number(spool.get("remaining_length"))
        if remaining is not None:
            return remaining
        weight = _finite_number(spool.get("remaining_weight"))
        if weight is None:
            return None
        filament = spool.get("filament")
        filament = filament if isinstance(filament, dict) else {}
        density = _finite_number(filament.get("density")) or 1.24
        diameter = _finite_number(filament.get("diameter")) or 1.75
        if density <= 0:
            return None
        area_mm2 = math.pi * (diameter / 2) ** 2
        # g / (g/cm3) = cm3 → mm = cm3 * 1000 / mm2
        return (weight / density) * 1000 / area_mm2

    def _analyze_spool(self) -> list[dict[str, str]]:
        data = self.coordinator.data or {}
        status = data.get("status") or {}
        spool = data.get("spool_details")
        if not isinstance(spool, dict) or not spool:
            self.metrics["spool_material"] = None
            self.metrics["spool_remaining_mm"] = None
            self.metrics["spool_runout_layer"] = None
            return []
        filament = spool.get("filament")
        filament = filament if isinstance(filament, dict) else {}
        material = str(filament.get("material") or "").strip().upper() or None
        self.metrics["spool_material"] = material
        remaining_mm = self._spool_remaining_mm(spool)
        self.metrics["spool_remaining_mm"] = (
            round(remaining_mm, 1) if remaining_mm is not None else None
        )
        findings: list[dict[str, str]] = []
        print_stats = status.get("print_stats") or {}
        printing = print_stats.get("state") in ("printing", "paused")
        filament_total = _finite_number(data.get("filament_total")) or 0.0
        filament_used = _finite_number(print_stats.get("filament_used")) or 0.0
        needed = filament_total - filament_used
        if printing and needed > 0 and remaining_mm is not None:
            if remaining_mm < needed / SPOOL_SHORT_RATIO:
                info = print_stats.get("info") or {}
                current_layer = _finite_number(info.get("current_layer")) or 0
                layer_count = _finite_number(data.get("layer_count")) or 0
                per_layer = filament_total / layer_count if layer_count else None
                runout = None
                if per_layer:
                    runout = current_layer + remaining_mm / per_layer
                self.metrics["spool_runout_layer"] = (
                    round(runout) if runout is not None else None
                )
                findings.append(
                    {
                        "severity": "warn",
                        "label": "spool shortfall",
                        "detail": (
                            f"the active spool holds ~{remaining_mm / 1000:.1f}m "
                            f"but ~{needed / 1000:.1f}m remains in this print"
                            + (
                                f" — runs out near layer {int(runout)}"
                                if runout
                                else ""
                            )
                        ),
                    }
                )
            else:
                self.metrics["spool_runout_layer"] = None
        else:
            self.metrics["spool_runout_layer"] = None
        file_type = str(data.get("filament_type") or "").strip().upper()
        if (
            printing
            and file_type
            and material
            and file_type not in material
            and material not in file_type
        ):
            findings.append(
                {
                    "severity": "warn",
                    "label": "material mismatch",
                    "detail": (
                        f"file was sliced for {file_type} but the active spool "
                        f"is {material}"
                    ),
                }
            )
        return findings

    # -- queue scheduling ---------------------------------------------------------

    def _analyze_queue_plan(self) -> list[dict[str, str]]:
        """Score queued jobs against the spool and suggest a better order."""
        data = self.coordinator.data or {}
        queue = data.get("queue") or {}
        jobs = queue.get("queued_jobs")
        if not isinstance(jobs, list) or not jobs:
            self.metrics["queue_plan"] = []
            self.metrics["queue_plan_differs"] = False
            self.metrics["queue_ambient_ready"] = None
            return []
        meta = data.get("queue_meta") or {}
        remaining_mm = self._spool_remaining_mm(data.get("spool_details") or {})
        material = self.metrics.get("spool_material")
        ambient = self._ambient_temp()
        material_upper = str(material or "").upper()
        cold_hold = (
            ambient is not None
            and ambient < CHAMBER_WARM_MIN_C
            and any(token in material_upper for token in HIGH_SHRINK_MATERIALS)
        )
        self.metrics["queue_ambient_ready"] = not cold_hold

        entries: list[dict[str, Any]] = []
        findings: list[dict[str, str]] = []
        for index, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            filename = str(job.get("filename") or "")
            job_meta = meta.get(filename) or {}
            filament_mm = _finite_number(job_meta.get("filament_total"))
            eta = _finite_number(job_meta.get("estimated_time"))
            file_type = str(job_meta.get("filament_type") or "").upper()
            reason = "shortest first"
            ok = True
            if (
                file_type
                and material
                and file_type not in material
                and material not in file_type
            ):
                ok = False
                reason = f"material mismatch: needs {file_type}"
            elif (
                filament_mm is not None
                and remaining_mm is not None
                and filament_mm > remaining_mm
            ):
                ok = False
                reason = "exceeds filament left on spool"
                findings.append(
                    {
                        "severity": "warn",
                        "label": "queued job exceeds spool",
                        "detail": (
                            f"{filename} needs ~{filament_mm / 1000:.1f}m but "
                            f"the spool holds ~{remaining_mm / 1000:.1f}m"
                        ),
                    }
                )
            entries.append(
                {
                    "job_id": str(job.get("job_id") or ""),
                    "filename": filename,
                    "eta_s": round(eta, 0) if eta is not None else None,
                    "filament_mm": (
                        round(filament_mm, 0) if filament_mm is not None else None
                    ),
                    "ok": ok,
                    "reason": reason,
                    "current_index": index,
                }
            )
        plan = sorted(
            entries,
            key=lambda item: (
                not item["ok"],
                item["eta_s"] if item["eta_s"] is not None else float("inf"),
                item["current_index"],
            ),
        )
        # Spool reservation: cumulative filament across runnable jobs must not
        # oversubscribe what is left on the spool.
        reserved_mm = 0.0
        ambient_held = False
        for item in plan:
            filament_mm = _finite_number(item.get("filament_mm"))
            item["ambient_hold"] = bool(cold_hold and item["ok"])
            if item["ambient_hold"]:
                ambient_held = True
            if not item["ok"] or filament_mm is None or remaining_mm is None:
                item["overruns_spool"] = False
                continue
            reserved_mm += filament_mm
            item["overruns_spool"] = reserved_mm > remaining_mm
            if item["overruns_spool"]:
                item["reason"] = "queue overruns spool when combined"
                findings.append(
                    {
                        "severity": "warn",
                        "label": "queue overruns spool",
                        "detail": (
                            f"{item['filename']} would run past the remaining "
                            f"~{remaining_mm / 1000:.1f}m of filament when "
                            "the queue is taken together"
                        ),
                    }
                )
        if ambient_held:
            findings.append(
                {
                    "severity": "warn",
                    "label": "ambient hold",
                    "detail": (
                        f"chamber at {ambient:.0f}°C is below the "
                        f"{CHAMBER_WARM_MIN_C:.0f}°C floor for {material_upper}"
                        " — warm the chamber before starting queued jobs"
                    ),
                }
            )
        self.metrics["queue_reserved_mm"] = round(reserved_mm, 0)
        self.metrics["queue_plan"] = plan
        self.metrics["queue_plan_differs"] = [item["job_id"] for item in plan] != [
            str(job.get("job_id") or "") for job in jobs if isinstance(job, dict)
        ][: len(plan)]
        return findings

    # -- material profiles + ambient ---------------------------------------------

    def _detect_material(self) -> str | None:
        data = self.coordinator.data or {}
        candidates = [
            data.get("filament_type"),
            self.metrics.get("spool_material"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            upper = str(candidate).upper()
            for name in MATERIAL_PROFILES:
                if name in upper:
                    return name
        return None

    def _ambient_temp(self) -> float | None:
        if not self.ambient_sensor:
            return None
        state = self.hass.states.get(self.ambient_sensor)
        if state is None:
            return None
        return _finite_number(state.state)

    def _analyze_material(self, status: dict[str, Any]) -> list[dict[str, str]]:
        material = self._detect_material()
        self.metrics["material"] = material
        ambient = self._ambient_temp()
        self.metrics["ambient_c"] = ambient
        print_stats = status.get("print_stats") or {}
        if print_stats.get("state") != "printing" or material is None:
            return []
        profile = MATERIAL_PROFILES[material]
        findings: list[dict[str, str]] = []
        extruder = status.get("extruder") or {}
        nozzle_target = _finite_number(extruder.get("target"))
        lo, hi = profile["nozzle"]
        if nozzle_target is not None and not (lo - 15 <= nozzle_target <= hi + 15):
            findings.append(
                {
                    "severity": "warn",
                    "label": "nozzle outside profile",
                    "detail": (
                        f"nozzle target {nozzle_target:.0f}°C is outside the "
                        f"typical {material} range {lo}-{hi}°C"
                    ),
                }
            )
        bed = status.get("heater_bed") or {}
        bed_target = _finite_number(bed.get("target"))
        lo, hi = profile["bed"]
        if bed_target is not None and not (lo - 15 <= bed_target <= hi + 15):
            findings.append(
                {
                    "severity": "warn",
                    "label": "bed outside profile",
                    "detail": (
                        f"bed target {bed_target:.0f}°C is outside the typical "
                        f"{material} range {lo}-{hi}°C"
                    ),
                }
            )
        if profile["enclosure"] and ambient is not None and ambient < AMBIENT_COLD_C:
            findings.append(
                {
                    "severity": "warn",
                    "label": "cold ambient",
                    "detail": (
                        f"{material} prints best with a warm enclosure but the "
                        f"ambient sensor reads {ambient:.1f}°C"
                    ),
                }
            )
        return findings

    # -- kinematic limits -----------------------------------------------------------

    def _analyze_kinematics(self, status: dict[str, Any]) -> list[dict[str, str]]:
        config = getattr(self.coordinator, "_config_settings", None) or {}
        settings = ((config.get("status") or {}).get("configfile") or {}).get(
            "settings"
        ) or {}
        printer_cfg = settings.get("printer") or {}
        shaper = settings.get("input_shaper") or {}
        max_velocity = _finite_number(printer_cfg.get("max_velocity"))
        self.metrics["max_velocity"] = max_velocity
        self.metrics["max_accel"] = _finite_number(printer_cfg.get("max_accel"))
        self.metrics["shaper_freq_x"] = _finite_number(shaper.get("shaper_freq_x"))
        print_stats = status.get("print_stats") or {}
        velocity = _finite_number(
            (status.get("motion_report") or {}).get("live_velocity")
        )
        over_limit = (
            print_stats.get("state") == "printing"
            and max_velocity is not None
            and velocity is not None
            and velocity > max_velocity * VELOCITY_OVER_LIMIT_RATIO
        )
        if not over_limit:
            self._over_limit_samples = 0
            return []
        self._over_limit_samples += 1
        if self._over_limit_samples < VELOCITY_OVER_LIMIT_SAMPLES:
            return []
        self._over_limit_samples = 0
        return [
            {
                "severity": "warn",
                "label": "velocity above limit",
                "detail": (
                    f"live velocity {velocity:.0f}mm/s exceeds the configured "
                    f"max_velocity {max_velocity:.0f}mm/s — check printer.cfg "
                    "kinematics and input-shaper settings"
                ),
            }
        ]

    # -- bed mesh drift ---------------------------------------------------------

    def _analyze_mesh(
        self, status: dict[str, Any], now: float | None = None
    ) -> list[dict[str, str]]:
        mesh = status.get("bed_mesh") or {}
        matrix = _matrix_from_mesh(mesh)
        if matrix is None:
            self.metrics["mesh_status"] = "unknown"
            return []
        if self._mesh_baseline is None:
            self._mesh_baseline = {"matrix": matrix, "at": _now_ts()}
            self._mark_dirty()
        baseline = self._mesh_baseline.get("matrix")
        drift = _drift_stats(matrix, baseline)
        self.metrics["mesh_rms_drift_mm"] = round(drift["rms"], 4)
        self.metrics["mesh_max_drift_mm"] = round(drift["max"], 4)
        if drift["rms"] >= MESH_RMS_DUE_MM or drift["max"] >= MESH_MAX_DUE_MM:
            status_value = "due"
        elif drift["rms"] >= MESH_RMS_WARN_MM or drift["max"] >= MESH_MAX_WARN_MM:
            status_value = "rising"
        else:
            status_value = "stable"
        self.metrics["mesh_status"] = status_value
        self.metrics["mesh_baseline_at"] = _iso(
            float(self._mesh_baseline.get("at") or 0)
        )
        return self._track_mesh_surface(matrix, now or _now_ts())

    def _track_mesh_surface(
        self, matrix: list[list[float]], now: float
    ) -> list[dict[str, str]]:
        """Decompose the mesh into tram tilt + surface, and keep a history.

        The fitted plane isolates frame tilt (tram) from the bed surface:
        if the tram shifts, the raw mesh changes everywhere while the
        residuals (waviness) stay identical.
        """
        stats = _mesh_surface_stats(matrix)
        self.metrics["mesh_tilt_a"] = round(stats["tilt_a"], 4)
        self.metrics["mesh_tilt_b"] = round(stats["tilt_b"], 4)
        self.metrics["mesh_corner_offsets"] = stats["corners"]
        self.metrics["mesh_surface_rms_mm"] = round(stats["residual_rms"], 4)

        findings: list[dict[str, str]] = []
        last = self.mesh_history[-1] if self.mesh_history else None
        if last and last.get("fp") == stats["fp"]:
            self.metrics["mesh_surface_delta_rms"] = round(
                _finite_number(last.get("residual_rms")) or 0.0, 4
            )
            self.metrics["mesh_tilt_delta"] = 0.0
            self.metrics["mesh_snapshots"] = len(self.mesh_history)
            return findings

        if last:
            prev_residuals = last.get("residuals")
            same_shape = (
                isinstance(prev_residuals, list)
                and len(prev_residuals) == len(stats["residuals"])
                and all(
                    isinstance(row, list) and len(row) == len(stats["residuals"][0])
                    for row in prev_residuals
                )
            )
            if same_shape:
                delta = _drift_stats(stats["residuals"], prev_residuals)
                self.metrics["mesh_surface_delta_rms"] = round(delta["rms"], 4)
            else:
                delta = {"rms": 0.0}
                self.metrics["mesh_surface_delta_rms"] = 0.0
            tilt_delta = abs(
                stats["tilt_a"] - (_finite_number(last.get("tilt_a")) or 0.0)
            ) + abs(stats["tilt_b"] - (_finite_number(last.get("tilt_b")) or 0.0))
            self.metrics["mesh_tilt_delta"] = round(tilt_delta, 4)
            if tilt_delta >= MESH_TILT_SHIFT_WARN:
                findings.append(
                    {
                        "severity": "warn",
                        "label": "tram shifted",
                        "detail": (
                            f"bed tilt changed by {tilt_delta * 1000:.0f}µm "
                            "since the last mesh — re-check corner tramming"
                        ),
                    }
                )
            elif delta["rms"] >= MESH_RMS_WARN_MM:
                severity = "bad" if delta["rms"] >= MESH_RMS_DUE_MM else "warn"
                findings.append(
                    {
                        "severity": severity,
                        "label": "bed surface changed",
                        "detail": (
                            f"surface shape moved {delta['rms'] * 1000:.0f}µm "
                            "RMS excluding tilt — the bed itself changed"
                        ),
                    }
                )
        else:
            self.metrics["mesh_surface_delta_rms"] = 0.0
            self.metrics["mesh_tilt_delta"] = 0.0

        self.mesh_history.append(
            {
                "at": _iso(now),
                "fp": stats["fp"],
                "matrix": matrix,
                "tilt_a": stats["tilt_a"],
                "tilt_b": stats["tilt_b"],
                "corners": stats["corners"],
                "residuals": stats["residuals"],
                "residual_rms": stats["residual_rms"],
            }
        )
        self.mesh_history = self.mesh_history[-MESH_HISTORY_LIMIT:]
        self.metrics["mesh_snapshots"] = len(self.mesh_history)
        self._mark_dirty()
        return findings

    def reset_mesh_baseline(self) -> bool:
        """Capture the current mesh as the new baseline."""
        status = (self.coordinator.data or {}).get("status") or {}
        matrix = _matrix_from_mesh(status.get("bed_mesh") or {})
        if matrix is None:
            return False
        self._mesh_baseline = {"matrix": matrix, "at": _now_ts()}
        self._mark_dirty()
        self._analyze_mesh(status, _now_ts())
        return True

    # -- print-science diagnostics ----------------------------------------------

    @staticmethod
    def _is_printing(status: dict[str, Any]) -> bool:
        return (status.get("print_stats") or {}).get("state") == "printing"

    def _current_layer(self, status: dict[str, Any]) -> float | None:
        info = (status.get("print_stats") or {}).get("info") or {}
        return _finite_number(info.get("current_layer"))

    def _analyze_layers(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        """Detect layer boundaries and periodic layer-time signatures (Z-banding)."""
        if not self._is_printing(status):
            self._layer_boundary = None
            return []
        layer = self._current_layer(status)
        position = (status.get("toolhead") or {}).get("position") or []
        z = _finite_number(position[2]) if len(position) > 2 else None
        boundary = self._layer_boundary
        if layer is not None and boundary and boundary.get("layer") is not None:
            if layer > boundary["layer"]:
                duration = now - boundary["at"]
                dz = (
                    z - boundary["z"]
                    if z is not None and boundary.get("z") is not None
                    else None
                )
                self._layer_times.append({"at": now, "duration": duration, "dz": dz})
                self._print_layer_durations.append(duration)
                self._layer_boundary = {"layer": layer, "z": z, "at": now}
            elif layer < boundary["layer"]:
                self._layer_boundary = {"layer": layer, "z": z, "at": now}
        elif layer is not None:
            self._layer_boundary = {"layer": layer, "z": z, "at": now}
        elif z is not None:
            # No layer metadata: use Z hops of >= 0.05mm while printing.
            prev_z = boundary["z"] if boundary else None
            if prev_z is None or z - prev_z >= 0.05:
                if prev_z is not None and boundary is not None:
                    self._layer_times.append(
                        {
                            "at": now,
                            "duration": now - boundary["at"],
                            "dz": z - prev_z,
                        }
                    )
                    self._print_layer_durations.append(now - boundary["at"])
                self._layer_boundary = {"layer": None, "z": z, "at": now}
            elif z < prev_z:
                self._layer_boundary = {"layer": None, "z": z, "at": now}

        samples = list(self._layer_times)
        if len(samples) < LAYER_PERIOD_MIN_LAYERS:
            self.metrics["z_banding_period_mm"] = None
            return []
        durations = [sample["duration"] for sample in samples[-40:]]
        mean = sum(durations) / len(durations)
        denom = sum((value - mean) ** 2 for value in durations)
        if denom <= 1e-9:
            self.metrics["z_banding_period_mm"] = None
            return []
        best_lag, best_corr = 0, 0.0
        for lag in range(1, min(11, len(durations) - 1)):
            num = sum(
                (durations[i] - mean) * (durations[i - lag] - mean)
                for i in range(lag, len(durations))
            )
            corr = num / denom
            if corr > best_corr:
                best_lag, best_corr = lag, corr
        if best_corr < LAYER_PERIOD_MIN_CORR or not best_lag:
            self.metrics["z_banding_period_mm"] = None
            return []
        dzs = [
            sample["dz"]
            for sample in samples[-len(durations) :]
            if _finite_number(sample.get("dz"))
        ]
        period_mm = round(best_lag * sum(dzs) / len(dzs), 2) if dzs else None
        self.metrics["z_banding_period_mm"] = period_mm
        return [
            {
                "severity": "warn",
                "label": "z banding signature",
                "detail": (
                    f"layer times repeat every {best_lag} layers"
                    + (f" (~{period_mm}mm)" if period_mm else "")
                    + " — check leadscrew/Z mechanics"
                ),
            }
        ]

    def _analyze_stutter(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        """Count extrusion reversals and probable extruder skips while printing."""
        findings: list[dict[str, str]] = []
        motion = status.get("motion_report") or {}
        ext_vel = _finite_number(motion.get("live_extruder_velocity")) or 0.0
        move_vel = _finite_number(motion.get("live_velocity")) or 0.0
        if not self._is_printing(status):
            self._prev_ext_velocity = ext_vel
            return findings
        if ext_vel > 1.5:
            self._last_extrusion_at = now
        # Sign reversal while commanded to move = a retraction or a stall.
        if self._prev_ext_velocity * ext_vel < 0:
            self._stutter_events.append(now)
        # Probable skip: was extruding recently, extrusion stalled, still moving.
        if (
            self._prev_ext_velocity > 2.0
            and ext_vel < 0.3
            and move_vel > 10
            and self._last_extrusion_at is not None
            and now - self._last_extrusion_at < 3
            and (not self._stutter_events or now - self._stutter_events[-1] > 1.0)
        ):
            self.extruder_skips += 1
            self._stutter_events.append(now)
        self._prev_ext_velocity = ext_vel
        window = [ts for ts in self._stutter_events if now - ts <= 60]
        self.metrics["extrusion_stutter_per_min"] = len(window)
        self.metrics["extruder_skips"] = self.extruder_skips
        if self.extruder_skips >= 3:
            findings.append(
                {
                    "severity": "bad",
                    "label": "extruder skipping",
                    "detail": (
                        f"{self.extruder_skips} probable skip events this print"
                        " — flow is stalling while the head keeps moving"
                    ),
                }
            )
        elif len(window) >= 30:
            findings.append(
                {
                    "severity": "warn",
                    "label": "extrusion stutter",
                    "detail": (
                        f"{len(window)} extrusion reversals in the last minute"
                        " — check pressure advance / nozzle condition"
                    ),
                }
            )
        return findings

    def _analyze_drivers(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        """Track stepper-driver temperatures and predict thermal shutdown."""
        hottest: float | None = None
        for name, section in status.items():
            if not (name.startswith("tmc") or "driver" in name):
                continue
            temp = _finite_number(section.get("temperature"))
            if temp is not None and (hottest is None or temp > hottest):
                hottest = temp
        self.metrics["driver_max_c"] = round(hottest, 1) if hottest else None
        if hottest is None:
            return []
        self._tmc_history.append((now, hottest))
        if hottest < DRIVER_TEMP_WARN_C or len(self._tmc_history) < 5:
            return []
        samples = [sample for sample in self._tmc_history if now - sample[0] <= 300]
        if len(samples) < 5:
            return []
        t0, t_start = samples[0]
        span = max(1.0, now - t0)
        slope = (hottest - t_start) / span * 60  # °C per minute
        if slope <= 0.5:
            return []
        eta = (DRIVER_TEMP_SHUTDOWN_C - hottest) / slope
        self.metrics["driver_shutdown_eta_min"] = round(eta, 1)
        if eta > 15:
            return []
        return [
            {
                "severity": "warn" if eta > 5 else "bad",
                "label": "driver overheating",
                "detail": (
                    f"stepper driver at {hottest:.0f}°C rising "
                    f"{slope:.1f}°C/min — thermal shutdown in ~{eta:.0f}min"
                ),
            }
        ]

    def _analyze_voltages(self, status: dict[str, Any]) -> list[dict[str, str]]:
        """Watch any reported rail voltage for sag below its baseline."""
        findings: list[dict[str, str]] = []
        seen: set[str] = set()
        for section in status.values():
            for key, value in section.items():
                lowered = key.lower()
                if not any(
                    token in lowered for token in ("voltage", "vbus", "vin", "vcc")
                ):
                    continue
                volts = _finite_number(value)
                if volts is None or volts <= 0 or volts > 1000:
                    continue
                label = f"{id(section)}.{key}"
                seen.add(label)
                if label not in self._voltage_baseline:
                    history = self._voltage_history.setdefault(label, deque(maxlen=40))
                    history.append(volts)
                    if len(history) >= 10:
                        ordered = sorted(history)
                        self._voltage_baseline[label] = ordered[len(ordered) // 2]
                    continue
                baseline = self._voltage_baseline[label]
                if baseline and volts < baseline * (1 - VOLTAGE_SAG_PCT / 100):
                    findings.append(
                        {
                            "severity": "warn",
                            "label": "voltage sag",
                            "detail": (
                                f"{key} dropped to {volts:.2f}V from a "
                                f"{baseline:.2f}V baseline — check PSU"
                            ),
                        }
                    )
        self.metrics["voltage_watch_count"] = len(seen)
        return findings

    def _analyze_thermistor_health(
        self, status: dict[str, Any], now: float
    ) -> list[dict[str, str]]:
        """Compare power-per-degree at steady state against history."""
        findings: list[dict[str, str]] = []
        for label, section in self._heater_objects(status):
            temp = _finite_number(section.get("temperature"))
            target = _finite_number(section.get("target"))
            power = _finite_number(section.get("power"))
            steady = (
                temp is not None
                and target is not None
                and target >= 40
                and abs(temp - target) <= 2
                and power is not None
                and 0.05 <= power <= 0.95
            )
            if not steady:
                self._steady_since.pop(label, None)
                continue
            since = self._steady_since.setdefault(label, now)
            if now - since < HEATER_STEADY_SECONDS:
                continue
            last = self._power_ratio_at.get(label, 0.0)
            if now - last < HEATER_STEADY_SECONDS:
                continue
            self._power_ratio_at[label] = now
            ratio = power / temp
            history = self.heater_power_history.setdefault(label, [])
            baseline = sorted(history)[len(history) // 2] if len(history) >= 4 else None
            history.append(ratio)
            del history[:-20]
            self._mark_dirty()
            if baseline and ratio > baseline * (1 + HEATER_EFFICIENCY_DRIFT_PCT / 100):
                findings.append(
                    {
                        "severity": "warn",
                        "label": "heater efficiency declining",
                        "detail": (
                            f"{label} needs {(ratio / baseline - 1) * 100:.0f}%"
                            " more power than usual for the same temperature"
                            " — thermistor or heater cartridge aging"
                        ),
                    }
                )
            if label == "extruder" and baseline:
                self.metrics["hotend_efficiency_pct"] = round(ratio / baseline * 100, 1)
        return findings

    def _track_first_layer_flow(self, status: dict[str, Any]) -> None:
        """Bin extruded filament by XY region during the first layer."""
        if not self._is_printing(status):
            return
        position = (status.get("toolhead") or {}).get("position") or []
        z = _finite_number(position[2]) if len(position) > 2 else None
        filament = _finite_number(
            (status.get("print_stats") or {}).get("filament_used")
        )
        if z is None or filament is None:
            return
        if z > FIRST_LAYER_Z_MAX_MM:
            if self._first_layer_bins:
                values = list(self._first_layer_bins.values())
                mean = sum(values) / len(values)
                if len(values) >= 4 and mean > 0:
                    variance = sum((value - mean) ** 2 for value in values) / len(
                        values
                    )
                    cv = math.sqrt(variance) / mean
                    self.metrics["first_layer_flow_cv"] = round(cv, 3)
                self._first_layer_bins = {}
            return
        prev = self._prev_filament_used
        self._prev_filament_used = filament
        if prev is None or filament <= prev:
            return
        x = _finite_number(position[0])
        y = _finite_number(position[1])
        if x is None or y is None:
            return
        key = f"{int(x // FIRST_LAYER_BIN_MM)},{int(y // FIRST_LAYER_BIN_MM)}"
        self._first_layer_bins[key] = (
            self._first_layer_bins.get(key, 0.0) + filament - prev
        )

    def _track_twin(self, status: dict[str, Any], now: float) -> None:
        """Accumulate this print's fingerprint and drift vs its golden run."""
        if not self._is_printing(status):
            self._prev_sample_at = None
            return
        flow = _finite_number(self.metrics.get("volumetric_flow_mm3"))
        if flow is not None and flow > 0:
            self._print_flow_sum += flow
            self._print_flow_count += 1
            self._print_peak_flow = max(self._print_peak_flow, flow)
        temp = _finite_number((status.get("extruder") or {}).get("temperature"))
        if temp is not None:
            self._print_temp_samples.append(temp)
            del self._print_temp_samples[:-600]
        filename = str((status.get("print_stats") or {}).get("filename") or "")
        golden = self.golden_runs.get(filename)
        if not golden or not self._print_layer_durations:
            self.metrics["twin_drift_pct"] = None
            return
        avg_layer = sum(self._print_layer_durations) / len(self._print_layer_durations)
        golden_layer = _finite_number(golden.get("avg_layer_s"))
        avg_flow = (
            self._print_flow_sum / self._print_flow_count
            if self._print_flow_count
            else None
        )
        golden_flow = _finite_number(golden.get("avg_flow_mm3"))
        deviations = []
        if golden_layer and golden_layer > 0:
            deviations.append(abs(avg_layer / golden_layer - 1))
        if golden_flow and golden_flow > 0 and avg_flow:
            deviations.append(abs(avg_flow / golden_flow - 1))
        self.metrics["twin_drift_pct"] = (
            round(sum(deviations) / len(deviations) * 100, 1) if deviations else None
        )

    def _record_telemetry(self, status: dict[str, Any], now: float) -> None:
        """Keep a short rolling telemetry ring for failure forensics."""
        if self._ring_last_at is not None and now - self._ring_last_at < 2.0:
            return
        self._ring_last_at = now
        print_stats = status.get("print_stats") or {}
        motion = status.get("motion_report") or {}
        info = print_stats.get("info") or {}
        position = (status.get("toolhead") or {}).get("position") or []
        self._telemetry_ring.append(
            {
                "t": round(now, 1),
                "state": print_stats.get("state"),
                "ext_t": _finite_number(
                    (status.get("extruder") or {}).get("temperature")
                ),
                "bed_t": _finite_number(
                    (status.get("heater_bed") or {}).get("temperature")
                ),
                "vel": _finite_number(motion.get("live_velocity")),
                "ext_vel": _finite_number(motion.get("live_extruder_velocity")),
                "layer": info.get("current_layer"),
                "z": _finite_number(position[2]) if len(position) > 2 else None,
            }
        )

    def _update_preflight(self, status: dict[str, Any], now: float) -> None:
        """Expose a passive pre-flight checklist in metrics."""
        data = self.coordinator.data or {}
        klippy = str((data.get("printer.info") or {}).get("state") or "unknown")
        checks: dict[str, Any] = {"klippy": klippy in ("ready", "startup")}
        extruder_temp = _finite_number(
            (status.get("extruder") or {}).get("temperature")
        )
        checks["nozzle_safe"] = extruder_temp is None or extruder_temp < 45
        if self.mesh_history:
            last_at = self.mesh_history[-1].get("at")
            try:
                stamp = datetime.fromisoformat(str(last_at)).timestamp()
                age_days = (now - stamp) / 86400
            except (TypeError, ValueError):
                age_days = None
            checks["mesh_age_days"] = (
                round(age_days, 1) if age_days is not None else None
            )
            checks["mesh_fresh"] = age_days is not None and age_days <= MESH_FRESH_DAYS
        else:
            checks["mesh_age_days"] = None
            checks["mesh_fresh"] = None
        remaining = self.metrics.get("spool_remaining_mm")
        needed = _finite_number(data.get("filament_total"))
        checks["spool_fits"] = (
            remaining is None or needed is None or needed <= 0 or remaining >= needed
        )
        checks["ready"] = all(
            value is not False
            for key, value in checks.items()
            if key != "mesh_age_days"
        )
        self.metrics["preflight"] = checks
        self.metrics["preflight_ready"] = checks["ready"]

    def _update_oee(self, status: dict[str, Any], now: float) -> None:
        """Track utilization, success rate, and throughput for OEE reporting."""
        if self._oee_last_at is not None:
            delta = now - self._oee_last_at
            if 0 < delta <= 600:
                self._oee_window_s += delta
                if self._is_printing(status):
                    self._oee_printing_s += delta
        self._oee_last_at = now
        if self._oee_window_s > 300:
            self.metrics["oee_utilization_pct"] = round(
                self._oee_printing_s / self._oee_window_s * 100, 1
            )
        else:
            self.metrics["oee_utilization_pct"] = None
        attempts = 0
        completed = 0
        for stats in self.file_stats.values():
            attempts += int(stats.get("attempts") or 0)
            completed += int(stats.get("completed") or 0)
        self.metrics["oee_success_rate_pct"] = (
            round(completed / attempts * 100, 1) if attempts else None
        )
        filament_mm = 0.0
        hours = 0.0
        for record in self.print_history:
            filament_mm += _finite_number(record.get("filament_used_mm")) or 0.0
            hours += (_finite_number(record.get("print_duration_s")) or 0.0) / 3600
        grams = filament_mm * FILAMENT_AREA_MM2 * 1.24 / 1000
        self.metrics["oee_throughput_gh"] = (
            round(grams / hours, 1) if hours > 0 else None
        )
        self.metrics["oee_tracked_prints"] = len(self.print_history)

    def track_config_drift(self, config: dict[str, Any]) -> None:
        """Hash the printer config and flag silent changes."""
        try:
            digest = hashlib.sha256(
                json.dumps(config, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
        except (TypeError, ValueError):
            return
        if self.config_hash is None:
            self.config_hash = digest
            self._mark_dirty()
            return
        if digest != self.config_hash:
            self.config_hash = digest
            self.config_changed_at = _iso(_now_ts())
            self._mark_dirty()
        self.metrics["config_changed_at"] = self.config_changed_at

    # -- energy -----------------------------------------------------------------

    def _read_power_watts(self) -> float | None:
        """Read the configured HA power sensor, converting kW to W."""
        if not self.power_sensor:
            return None
        state = self.hass.states.get(self.power_sensor)
        if state is None:
            return None
        watts = _finite_number(state.state)
        if watts is None:
            return None
        unit = str(state.attributes.get("unit_of_measurement") or "W").lower()
        return watts * 1000 if unit == "kw" else watts

    def _track_energy(self, status: dict[str, Any], now: float) -> None:
        watts = self._read_power_watts()
        print_stats = status.get("print_stats") or {}
        state = print_stats.get("state")
        filename = str(print_stats.get("filename") or "")
        active = state in ("printing", "paused")
        if active and watts is not None:
            session = self.energy_session
            if session["filename"] != filename:
                session.update({"filename": filename, "kwh": 0.0, "last_at": now})
            last_at = session.get("last_at") or now
            dt_hours = (now - float(last_at)) / 3600
            if 0 < dt_hours < 1:
                session["kwh"] += watts * dt_hours / 1000
                self.total_kwh += watts * dt_hours / 1000
                self._mark_dirty()
            session["last_at"] = now
        self.metrics["power_watts"] = round(watts, 1) if watts is not None else None
        self.metrics["print_energy_kwh"] = round(self.energy_session["kwh"], 4)
        self.metrics["print_cost"] = (
            round(self.energy_session["kwh"] * self.energy_rate, 4)
            if self.energy_rate > 0
            else None
        )
        self.metrics["total_kwh"] = round(self.total_kwh, 4)

    # -- print history ----------------------------------------------------------

    def _track_print_state(
        self,
        status: dict[str, Any],
        now: float,
        findings: list[dict[str, str]],
    ) -> None:
        print_stats = status.get("print_stats") or {}
        state = print_stats.get("state")
        filename = str(print_stats.get("filename") or "")
        if state == "printing" and self._prev_print_state != "printing":
            if self._prev_print_state != "paused":
                self._print_started_at = now
                self._print_faults = set()
                self._vision_alerts = []
                self._first_layer_checked_for = None
                self._last_vision_check = None
                self.checkpoints.clear()
                self._last_checkpoint_at = None
                self._reset_print_tracking(now, filename, findings)
                self._dispatch_print_event("print_started", filename)
            else:
                self._dispatch_print_event("print_resumed", filename)
        elif state == "paused" and self._prev_print_state == "printing":
            self._dispatch_print_event("print_paused", filename)
        for finding in findings:
            if finding["severity"] in ("warn", "bad"):
                self._print_faults.add(finding["label"])
        if state in ("complete", "cancelled", "error") and self._prev_print_state in (
            "printing",
            "paused",
        ):
            self._record_print(status, state, now)
            self._dispatch_print_event(
                _PRINT_STATE_EVENTS.get(state, f"print_{state}"), filename
            )
            if state == "complete":
                self._schedule_power_off()
                self._schedule_caption(filename)
        self._prev_print_state = state

    def _dispatch_print_event(self, event_type: str, filename: str) -> None:
        """Fan out a lifecycle event to the event entity and notifications."""
        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_PRINT_EVENT}_{self.coordinator.config_entry.entry_id}",
            {"type": event_type, "filename": filename},
        )
        self._notify(event_type, filename)

    def _notify(self, event_type: str, filename: str) -> None:
        """Send an optional companion-app notification on print milestones."""
        if not self.notify_service:
            return
        titles = {
            "print_started": "Print started",
            "print_resumed": "Print resumed",
            "print_paused": "Print paused",
            "print_completed": "Print completed",
            "print_cancelled": "Print cancelled",
            "print_error": "Print error",
            "vision_alert": "Print problem detected",
        }
        title = titles.get(event_type, "Printer event")
        data: dict[str, Any] = {"title": title, "message": f"{title}: {filename}"}
        if event_type in ("print_started", "print_resumed", "print_paused"):
            data["data"] = {
                "actions": [
                    {"action": "PAUSE", "title": "Pause"},
                    {"action": "CANCEL", "title": "Cancel"},
                ]
            }
        self.hass.async_create_task(self._async_notify(data))

    async def _async_notify(self, data: dict[str, Any]) -> None:
        """Call the notify service, tolerating missing handlers."""
        try:
            await self.hass.services.async_call("notify", self.notify_service, data)
        except Exception:  # noqa: BLE001 - notify targets can disappear
            _LOGGER.debug("Notify service %s unavailable", self.notify_service)

    # -- vision checks + recovery checkpoints ----------------------------------

    def _vision_enabled(self) -> bool:
        """Vision checks need both an ai_task entity and a camera to attach."""
        return bool(self.ai_task_entity and self.vision_camera)

    def _maybe_schedule_vision(self, status: dict[str, Any], now: float) -> None:
        """Kick off periodic and first-layer vision checks while printing."""
        print_stats = status.get("print_stats") or {}
        if not self._vision_enabled() or print_stats.get("state") != "printing":
            return
        if self._vision_task is not None and not self._vision_task.done():
            return
        filename = str(print_stats.get("filename") or "")
        info = print_stats.get("info") or {}
        current_layer = _finite_number(info.get("current_layer"))
        if (
            current_layer is not None
            and current_layer >= 2
            and self._first_layer_checked_for != filename
        ):
            self._first_layer_checked_for = filename
            self._last_vision_check = now
            self._vision_task = self.hass.async_create_task(
                self._async_vision_check("first_layer", _FIRST_LAYER_PROMPT)
            )
            return
        if (
            self._last_vision_check is None
            or now - self._last_vision_check >= VISION_INTERVAL_SECONDS
        ):
            self._last_vision_check = now
            self._vision_task = self.hass.async_create_task(
                self._async_vision_check("spaghetti", _SPAGHETTI_PROMPT)
            )

    async def _async_ai_task(self, prompt: str) -> str | None:
        """Run the configured ai_task entity on the camera frame."""
        try:
            response = await self.hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": VISION_TASK_NAME,
                    "instructions": prompt,
                    "entity_id": self.ai_task_entity,
                    "attachments": {
                        "media_content_id": (
                            f"media-source://camera/{self.vision_camera}"
                        ),
                        "media_content_type": "image/jpeg",
                    },
                },
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001 - ai_task is best-effort
            _LOGGER.debug("ai_task request failed", exc_info=True)
            return None
        return str((response or {}).get("data") or "").strip() or None

    async def _async_vision_check(self, kind: str, prompt: str) -> None:
        """Ask the configured ai_task entity to judge the camera frame."""
        verdict = str(await self._async_ai_task(prompt) or "").upper()
        if "FAIL" not in verdict:
            return
        detail = (
            "first layer shows adhesion gaps or air printing"
            if kind == "first_layer"
            else "camera shows possible print failure (spaghetti or detached part)"
        )
        alert = {
            "severity": "bad",
            "label": f"vision {kind}",
            "detail": f"camera analysis: {detail}",
        }
        if alert not in self._vision_alerts:
            self._vision_alerts.append(alert)
        print_stats = ((self.coordinator.data or {}).get("status") or {}).get(
            "print_stats"
        ) or {}
        self._notify("vision_alert", str(print_stats.get("filename") or ""))
        self._sync_repairs()

    def _schedule_caption(self, filename: str) -> None:
        """Queue an AI caption for the just-finished print, if configured."""
        if not filename or not self._vision_enabled():
            return
        if self._vision_task is not None and not self._vision_task.done():
            return
        self._vision_task = self.hass.async_create_task(self._async_caption(filename))

    async def _async_caption(self, filename: str) -> None:
        """Attach an AI-generated caption to the last print record."""
        caption = await self._async_ai_task(_CAPTION_PROMPT)
        if not caption:
            return
        for record in reversed(self.print_history):
            if record.get("filename") == filename:
                record["caption"] = caption
                break
        self.metrics["last_print_caption"] = caption
        self._mark_dirty()

    def _track_checkpoints(self, status: dict[str, Any], now: float) -> None:
        """Record periodic recovery checkpoints during a print."""
        print_stats = status.get("print_stats") or {}
        if print_stats.get("state") != "printing":
            return
        if (
            self._last_checkpoint_at is not None
            and now - self._last_checkpoint_at < CHECKPOINT_INTERVAL_SECONDS
        ):
            return
        self._last_checkpoint_at = now
        info = print_stats.get("info") or {}
        position = ((status.get("toolhead") or {}).get("position") or [None] * 4)[:4]
        extruder = status.get("extruder") or {}
        bed = status.get("heater_bed") or {}
        self._mark_dirty()
        self.checkpoints.append(
            {
                "at": _iso(now),
                "layer": info.get("current_layer"),
                "position": position,
                "nozzle_c": _finite_number(extruder.get("temperature")),
                "bed_c": _finite_number(bed.get("temperature")),
                "filament_used_mm": _finite_number(print_stats.get("filament_used")),
            }
        )

    def _schedule_power_off(self) -> None:
        """Arm the delayed printer power-off after a completed print."""
        if not self.power_switch or self._power_off_armed:
            return
        self._power_off_armed = True
        self._power_off_unsub = async_call_later(
            self.hass,
            timedelta(minutes=self.power_off_delay),
            self._async_power_off_check,
        )

    async def _async_power_off_check(self, _now: Any = None) -> None:
        """Switch the printer off once cooled and the queue is empty."""
        self._power_off_unsub = None
        try:
            data = self.coordinator.data or {}
            status = data.get("status") or {}
            print_state = (status.get("print_stats") or {}).get("state")
            extruder_temp = _finite_number(
                (status.get("extruder") or {}).get("temperature")
            )
            queue = data.get("queue") or {}
            queued_jobs = queue.get("queued_jobs") or queue.get("queue") or []
            if print_state in ("printing", "paused"):
                return
            if extruder_temp is not None and extruder_temp > self.power_off_max_temp:
                _LOGGER.info("Postponing power-off: hotend at %.0f°C", extruder_temp)
                return
            if queued_jobs:
                return
            _LOGGER.info("Powering off %s after completed print", self.power_switch)
            try:
                await self.hass.services.async_call(
                    "switch", "turn_off", {"entity_id": self.power_switch}
                )
            except Exception:  # noqa: BLE001 - switch entity may be gone
                _LOGGER.warning("Power switch %s unavailable", self.power_switch)
        finally:
            self._power_off_armed = False

    def _sync_repairs(self) -> None:
        """Mirror findings into HA Repairs issues."""
        entry_id = self.coordinator.config_entry.entry_id

        def sync(issue_key: str, active: bool, severity: str) -> None:
            issue_id = f"{entry_id}_{issue_key}"
            if active:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=(
                        ir.IssueSeverity.WARNING
                        if severity == "warn"
                        else ir.IssueSeverity.ERROR
                    ),
                    translation_key=issue_key,
                    translation_placeholders={
                        "printer": self.coordinator.api_device_name
                    },
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

        sync("mesh_relevel", self.metrics.get("mesh_status") == "due", "warn")
        sync(
            "heater_anomaly",
            any(
                finding["severity"] == "bad" and "saturated" in finding["label"]
                for finding in self.findings
            ),
            "error",
        )
        sync(
            "extrusion_stall",
            any("stall" in finding["label"] for finding in self.findings),
            "error",
        )
        sync(
            "slow_heatup",
            any("slow heat-up" in finding["label"] for finding in self.findings),
            "warn",
        )
        sync(
            "spool_shortfall",
            any("spool shortfall" in finding["label"] for finding in self.findings),
            "warn",
        )
        sync(
            "vision_alert",
            any("vision" in finding["label"] for finding in self.findings)
            or bool(self._vision_alerts),
            "error",
        )
        machine_update = (self.coordinator.data or {}).get("machine_update") or {}
        version_info = machine_update.get("version_info") or {}
        updates_pending = any(
            isinstance(info, dict)
            and info.get("remote_version") is not None
            and info.get("remote_version") != info.get("version")
            for info in version_info.values()
        ) or (
            isinstance(version_info.get("system"), dict)
            and (version_info["system"].get("package_count") or 0) > 0
        )
        sync("updates_available", updates_pending, "warn")
        sync(
            "printer_unreachable",
            not self.coordinator.last_update_success,
            "warn",
        )
        config_recent = False
        if self.config_changed_at:
            try:
                stamp = datetime.fromisoformat(self.config_changed_at).timestamp()
                config_recent = (_now_ts() - stamp) < 7 * 86400
            except (TypeError, ValueError):
                config_recent = False
        sync("config_changed", config_recent, "warn")
        sync(
            "moisture_risk",
            any(
                "filament moisture risk" in finding["label"]
                for finding in self.findings
            ),
            "warn",
        )
        sync(
            "extrusion_drift",
            any("extrusion drift" in finding["label"] for finding in self.findings),
            "warn",
        )

    def _reset_print_tracking(
        self, now: float, filename: str, findings: list[dict[str, str]]
    ) -> None:
        """Reset per-print accumulators and update file history on a new job."""
        self._layer_boundary = None
        self._print_layer_durations = []
        self._first_layer_bins = {}
        self._prev_filament_used = None
        self.extruder_skips = 0
        self._stutter_events.clear()
        self._prev_ext_velocity = 0.0
        self._last_extrusion_at = None
        self._print_flow_sum = 0.0
        self._print_flow_count = 0
        self._print_peak_flow = 0.0
        self._print_temp_samples = []
        self._telemetry_ring.clear()
        self._ring_last_at = None
        self._print_start_ambient = self._ambient_temp()

        material = str(self.metrics.get("spool_material") or "")
        ambient = self._print_start_ambient
        if (
            ambient is not None
            and ambient < CHAMBER_WARM_MIN_C
            and any(token in material for token in HIGH_SHRINK_MATERIALS)
        ):
            findings.append(
                {
                    "severity": "warn",
                    "label": "warp risk",
                    "detail": (
                        f"{material} starting in a {ambient:.0f}°C chamber"
                        " — historical warp failures correlate with cold starts"
                    ),
                }
            )

        stats = self.file_stats.get(filename)
        if stats is None:
            stats = {"attempts": 0, "completed": 0, "faults": []}
            self.file_stats[filename] = stats
            if len(self.file_stats) > FILE_STATS_LIMIT:
                oldest = next(iter(self.file_stats))
                del self.file_stats[oldest]
        stats["attempts"] = int(stats.get("attempts") or 0) + 1
        past_faults = [f for f in stats.get("faults") or [] if f]
        attempts = int(stats.get("attempts") or 1)
        completed = int(stats.get("completed") or 0)
        if past_faults and attempts > completed:
            findings.append(
                {
                    "severity": "warn",
                    "label": "file history",
                    "detail": (
                        f"{filename} completed {completed}/{attempts - 1} "
                        f"previous attempts — last faults: {', '.join(past_faults[-3:])}"
                    ),
                }
            )
        self._mark_dirty()

    def _record_print(self, status: dict[str, Any], state: str, now: float) -> None:
        print_stats = status.get("print_stats") or {}
        data = self.coordinator.data or {}
        estimated = _finite_number(data.get("estimated_time"))
        duration = _finite_number(print_stats.get("print_duration")) or 0.0
        record = {
            "filename": str(print_stats.get("filename") or ""),
            "state": state,
            "finished_at": _iso(now),
            "started_at": _iso(self._print_started_at or now),
            "print_duration_s": round(duration, 1),
            "total_duration_s": round(
                _finite_number(print_stats.get("total_duration")) or 0.0, 1
            ),
            "filament_used_mm": round(
                _finite_number(print_stats.get("filament_used")) or 0.0, 1
            ),
            "estimated_time_s": round(estimated, 1) if estimated else None,
            "estimate_delta_pct": (
                round((duration / estimated - 1) * 100, 1)
                if estimated and estimated > 0
                else None
            ),
            "energy_kwh": round(self.energy_session["kwh"], 4),
            "cost": (
                round(self.energy_session["kwh"] * self.energy_rate, 4)
                if self.energy_rate > 0
                else None
            ),
            "faults": sorted(self._print_faults),
            "checkpoints": list(self.checkpoints)[-CHECKPOINT_KEPT_ON_RECORD:],
        }
        filename = record["filename"]

        # Scorecard: deduct for faults, skips, and twin drift.
        score = 100 - 15 * len(record["faults"])
        twin_drift = _finite_number(self.metrics.get("twin_drift_pct"))
        if twin_drift and twin_drift > 10:
            score -= 20
        if self.extruder_skips >= 3:
            score -= 10
        score = max(0, min(100, score))
        grade = (
            "A"
            if score >= 90
            else "B"
            if score >= 75
            else "C"
            if score >= 60
            else "D"
            if score >= 40
            else "F"
        )
        record["grade"] = grade
        record["score"] = score
        self.metrics["print_grade"] = grade

        # Per-file ETA learning: remember the observed correction factor.
        if estimated and estimated > 0 and duration > 0 and state == "complete":
            material = str(self.metrics.get("spool_material") or "")
            key = f"{filename}|{material}"
            previous = self.eta_factors.get(key)
            factor = duration / estimated
            self.eta_factors[key] = (
                round(0.7 * previous + 0.3 * factor, 4)
                if previous
                else round(factor, 4)
            )
            self.metrics["eta_factor"] = self.eta_factors[key]

        # Nozzle-wear signal: peak flow ceiling per material, per print.
        if state == "complete" and self._print_peak_flow > 0:
            material = str(self.metrics.get("spool_material") or "unknown")
            peaks = self.flow_peaks.setdefault(material, [])
            peaks.append(round(self._print_peak_flow, 2))
            del peaks[:-10]
            if len(peaks) >= 4:
                baseline = sorted(peaks[:-1])[len(peaks[:-1]) // 2]
                if peaks[-1] < baseline * (1 - NOZZLE_WEAR_DROP_PCT / 100):
                    record.setdefault("faults", []).append("nozzle wear?")

        # Forensics: keep the last telemetry window on non-clean finishes.
        if state != "complete":
            record["forensics"] = {
                "telemetry": list(self._telemetry_ring),
                "findings": [dict(f) for f in self.findings],
                "ambient_at_start_c": self._print_start_ambient,
            }

        # Golden-run bookkeeping: keep the best completed fingerprint per file.
        if state == "complete" and self._print_layer_durations:
            avg_layer = sum(self._print_layer_durations) / len(
                self._print_layer_durations
            )
            avg_flow = (
                self._print_flow_sum / self._print_flow_count
                if self._print_flow_count
                else None
            )
            temps = self._print_temp_samples
            temp_stdev = statistics.pstdev(temps[-300:]) if len(temps) >= 30 else None
            fingerprint = {
                "avg_layer_s": round(avg_layer, 2),
                "avg_flow_mm3": round(avg_flow, 3) if avg_flow else None,
                "temp_stdev_c": round(temp_stdev, 3) if temp_stdev else None,
                "duration_s": round(duration, 1),
                "faults": len(record["faults"]),
                "recorded_at": record["finished_at"],
            }
            golden = self.golden_runs.get(filename)
            better = (
                golden is None
                or len(record["faults"]) < int(golden.get("faults") or 0)
                or (
                    len(record["faults"]) == int(golden.get("faults") or 0)
                    and duration < (_finite_number(golden.get("duration_s")) or 1e9)
                )
            )
            if better:
                self.golden_runs[filename] = fingerprint
                if len(self.golden_runs) > TWIN_HISTORY_LIMIT:
                    del self.golden_runs[next(iter(self.golden_runs))]

        # File memory: mark completion outcome.
        stats = self.file_stats.setdefault(
            filename, {"attempts": 0, "completed": 0, "faults": []}
        )
        if state == "complete":
            stats["completed"] = int(stats.get("completed") or 0) + 1
        else:
            stats["faults"] = (stats.get("faults") or []) + sorted(self._print_faults)
            del stats["faults"][:-10]
        if len(self.file_stats) > FILE_STATS_LIMIT:
            del self.file_stats[next(iter(self.file_stats))]

        if state == "complete":
            self.printcast.record_mass(
                filename,
                _finite_number(data.get("filament_total")),
                _finite_number(print_stats.get("filament_used")),
            )
        self.print_history.append(record)
        self.print_history = self.print_history[-PRINT_HISTORY_LIMIT:]
        self._mark_dirty()
        _LOGGER.debug(
            "Recorded %s print of %s (%.0fs, %d faults)",
            state,
            record["filename"],
            duration,
            len(record["faults"]),
        )

    # -- diagnostics -----------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of analyzer state for diagnostics."""
        return {
            "metrics": dict(self.metrics),
            "findings": list(self.findings),
            "mesh_baseline_at": self.metrics.get("mesh_baseline_at"),
            "thermal_history_lengths": {
                name: len(samples) for name, samples in self.thermal_history.items()
            },
            "print_history": list(self.print_history),
            "mesh_history": [dict(record) for record in self.mesh_history],
            "file_stats": dict(self.file_stats),
            "golden_runs": dict(self.golden_runs),
            "eta_factors": dict(self.eta_factors),
            "energy_session": dict(self.energy_session),
            "printcast": dict(self.printcast.forecast),
            "spool_dose": dict(self.printcast.spool_dose),
            "mass_ledger": list(self.printcast.mass_ledger),
            "config": {
                "max_flow_mm3": self.max_flow_mm3,
                "energy_rate": self.energy_rate,
                "power_sensor": self.power_sensor,
            },
        }
