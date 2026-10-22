"""Server-side telemetry analyzer for Moonraker printers.

Derives health findings, flow, bed-mesh drift, energy, and per-print history
from the coordinator's already-subscribed status objects so detection keeps
working without any browser panel open. All state is per config entry and
persisted through Home Assistant's Store.
"""

from __future__ import annotations

import logging
import math
import re
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    CONF_OPTION_ENERGY_RATE,
    CONF_OPTION_MAX_FLOW,
    CONF_OPTION_POWER_SENSOR,
    DEFAULT_MAX_FLOW_MM3,
    DOMAIN,
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

_HEATER_GENERIC_RE = re.compile(r"^heater_generic (.+)$")
_MCU_RE = re.compile(r"^mcu")


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
                }
            )
        except Exception:  # noqa: BLE001 - persistence failure is non-fatal
            _LOGGER.warning("Could not save analyzer store")

    async def async_shutdown(self) -> None:
        """Cancel the debounce timer and persist pending state on unload."""
        if self._save_unsub is not None:
            self._save_unsub()
            self._save_unsub = None
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
        findings: list[dict[str, str]] = []
        findings.extend(self._analyze_thermal(status, now))
        findings.extend(self._analyze_flow(status, now))
        findings.extend(self._analyze_retransmits(status, now))
        findings.extend(self._analyze_extrusion_stall(status, now))
        self._analyze_mesh(status)
        self._track_energy(status, now)
        self._track_print_state(status, now, findings)
        self.findings = findings

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
        if state == "printing" and self._prev_print_state != "printing":
            if self._prev_print_state != "paused":
                self._print_started_at = now
                self._print_faults = set()
        for finding in findings:
            if finding["severity"] in ("warn", "bad"):
                self._print_faults.add(finding["label"])
        if state in ("complete", "cancelled", "error") and self._prev_print_state in (
            "printing",
            "paused",
        ):
            self._record_print(status, state, now)
        self._prev_print_state = state

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
