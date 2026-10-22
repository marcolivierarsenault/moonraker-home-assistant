"""Server-side telemetry analyzer for Moonraker printers.

Derives health findings, flow, bed-mesh drift, energy, and per-print history
from the coordinator's already-subscribed status objects so detection keeps
working without any browser panel open. All state is per config entry and
persisted through Home Assistant's Store.
"""

from __future__ import annotations

import asyncio
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
                    "print_history": self.print_history[-PRINT_HISTORY_LIMIT:],
                    "total_kwh": round(self.total_kwh, 6),
                    "heatup_history": self._heatup_history,
                    "checkpoints": list(self.checkpoints),
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
        self._analyze_mesh(status)
        findings.extend(self._analyze_kinematics(status))
        self._track_energy(status, now)
        self._track_print_state(status, now, findings)
        self._track_checkpoints(status, now)
        self._maybe_schedule_vision(status, now)
        findings.extend(self._analyze_queue_plan())
        findings.extend(self._vision_alerts)
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
            return []
        meta = data.get("queue_meta") or {}
        remaining_mm = self._spool_remaining_mm(data.get("spool_details") or {})
        material = self.metrics.get("spool_material")

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

    def _analyze_mesh(self, status: dict[str, Any]) -> None:
        mesh = status.get("bed_mesh") or {}
        matrix = _matrix_from_mesh(mesh)
        if matrix is None:
            self.metrics["mesh_status"] = "unknown"
            return
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

    def reset_mesh_baseline(self) -> bool:
        """Capture the current mesh as the new baseline."""
        status = (self.coordinator.data or {}).get("status") or {}
        matrix = _matrix_from_mesh(status.get("bed_mesh") or {})
        if matrix is None:
            return False
        self._mesh_baseline = {"matrix": matrix, "at": _now_ts()}
        self._mark_dirty()
        self._analyze_mesh(status)
        return True

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

    async def _async_vision_check(self, kind: str, prompt: str) -> None:
        """Ask the configured ai_task entity to judge the camera frame."""
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
        except Exception as exception:  # noqa: BLE001 - vision is best-effort
            _LOGGER.debug("Vision check %s failed: %s", kind, exception)
            return
        verdict = str((response or {}).get("data") or "").upper()
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
            "energy_session": dict(self.energy_session),
            "config": {
                "max_flow_mm3": self.max_flow_mm3,
                "energy_rate": self.energy_rate,
                "power_sensor": self.power_sensor,
            },
        }
