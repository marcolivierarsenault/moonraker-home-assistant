"""Printcast: predictive print forecasting for Moonraker printers.

Forecasting instead of monitoring: before a job starts, Printcast scores the
selected file against everything the analyzer already knows — spool fit and
moisture dose, mesh freshness, file history, ambient conditions, extrusion
drift — and reports a Printability Index (0-100) with named risk factors and
the recommendation that recovers the most points.

Two measurements are unique to Printcast:

- Filament Hydration Dose: cumulative humidity exposure (RH-hours above 40 %)
  accrued by the active Spoolman spool, persisted per spool id.
- Mass Ledger / Extrusion Debt: slicer-declared vs. reported filament mass on
  completed prints, tracked against a learned per-printer baseline.

The engine is passive: it only reads coordinator data and HA states, and its
single bookkeeping action (mark_dried) never touches the printer.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import logging
import math
import statistics
from typing import Any

from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_OPTION_HUMIDITY_SENSOR, SIGNAL_PRINTCAST

_LOGGER = logging.getLogger(__name__)

# Hydration dose: RH-hours above this storage baseline count toward saturation.
DRY_STORAGE_RH = 40.0
# Dose thresholds (RH-hours) at which a spool counts as 100% saturated,
# grouped by how aggressively each material absorbs moisture.
MOISTURE_THRESHOLD_RH_H: dict[str, float] = {
    "PA": 40.0,
    "PC": 40.0,
    "PVA": 40.0,
    "TPU": 80.0,
    "PETG": 80.0,
    "ABS": 120.0,
    "ASA": 120.0,
    "PLA": 160.0,
}
DEFAULT_MOISTURE_THRESHOLD = 160.0
HUMIDITY_SAMPLE_GAP_MAX_S = 6 * 3600
SPOOL_DOSE_LIMIT = 24
SPOOL_UNTRACKED_HOURS = 24.0
MOISTURE_WARN_SATURATION_PCT = 70.0
HYGROSCOPIC_MATERIALS = ("PA", "PC", "PVA", "TPU", "PETG", "ABS", "ASA")

# Mass ledger: deviation of EMA below the learned baseline flags drift.
MASS_LEDGER_LIMIT = 30
LEDGER_ARMED_PRINTS = 5
LEDGER_DRIFT_PTS = 4.0

# Printability verdict boundaries.
VERDICT_CLEAR = 85
VERDICT_CAUTION = 60
VERDICT_POOR = 40

# Hard failures that always produce a NO-GO verdict regardless of score.
_NO_GO_FINDINGS = ("spool shortfall",)
_RISK_FINDINGS = ("driver overheating", "voltage sag")
_MESH_DRIFT_FINDINGS = ("tram shifted", "bed surface changed")
_LIVE_ONLY_LABEL = "live"


def _finite_number(value: Any) -> float | None:
    """Coerce a value to a finite float or return None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso(ts: float) -> str:
    """Format a UNIX timestamp as ISO-8601."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _material_key(name: str | None) -> str | None:
    """Normalize a material string to a threshold-table key."""
    if not name:
        return None
    upper = str(name).upper()
    for key in MOISTURE_THRESHOLD_RH_H:
        if key in upper:
            return key
    if "NYLON" in upper:
        return "PA"
    return None


class MoonrakerPrintcast:
    """Compute Printability forecasts from analyzer and coordinator state."""

    def __init__(self, analyzer: Any, mark_dirty: Callable[[], None]) -> None:
        """Bind to one analyzer instance; mark_dirty schedules persistence."""
        self.analyzer = analyzer
        self.hass = analyzer.hass
        self.coordinator = analyzer.coordinator
        options = analyzer.coordinator.config_entry.options
        self.humidity_sensor = str(options.get(CONF_OPTION_HUMIDITY_SENSOR) or "")
        self._mark_dirty = mark_dirty

        self.spool_dose: dict[str, dict[str, Any]] = {}
        self.mass_ledger: deque[dict[str, Any]] = deque(maxlen=MASS_LEDGER_LIMIT)
        self.debt_ema: float | None = None
        self._dose_last_at: float | None = None
        self._last_selected: str | None = None
        self._last_announced: dict[str, str] = {}
        self.forecast: dict[str, Any] = {}

    # -- persistence -----------------------------------------------------------

    def load_state(self, stored: dict[str, Any]) -> None:
        """Restore printcast state from the analyzer store payload."""
        dose = stored.get("spool_dose")
        if isinstance(dose, dict):
            self.spool_dose = {
                str(spool_id): dict(record)
                for spool_id, record in list(dose.items())[-SPOOL_DOSE_LIMIT:]
                if isinstance(record, dict)
            }
        ledger = stored.get("mass_ledger")
        if isinstance(ledger, list):
            self.mass_ledger = deque(
                [dict(entry) for entry in ledger if isinstance(entry, dict)],
                maxlen=MASS_LEDGER_LIMIT,
            )
        self.debt_ema = _finite_number(stored.get("extrusion_debt_ema"))
        announced = stored.get("printcast_last_announce")
        if isinstance(announced, dict):
            self._last_announced = {
                str(key): str(value) for key, value in announced.items()
            }

    def dump_state(self) -> dict[str, Any]:
        """Return the JSON-safe state written into the analyzer store."""
        return {
            "spool_dose": self.spool_dose,
            "mass_ledger": list(self.mass_ledger),
            "extrusion_debt_ema": self.debt_ema,
            "printcast_last_announce": self._last_announced,
        }

    # -- humidity + hydration dose ----------------------------------------------

    def _humidity_pct(self, status: dict[str, Any]) -> float | None:
        """Resolve humidity: configured sensor, else a Klipper env sensor."""
        if self.humidity_sensor:
            state = self.hass.states.get(self.humidity_sensor)
            if state is not None:
                value = _finite_number(state.state)
                if value is not None:
                    return value
        for section in status.values():
            if isinstance(section, dict):
                value = _finite_number(section.get("humidity"))
                if value is not None and 0 <= value <= 100:
                    return value
        return None

    def _active_spool(self) -> tuple[str | None, dict[str, Any]]:
        """Return the active Spoolman spool id and details dict."""
        data = self.coordinator.data or {}
        spool = data.get("spool_details")
        if not isinstance(spool, dict) or not spool:
            return None, {}
        spool_id = spool.get("id")
        return (str(spool_id) if spool_id is not None else None), spool

    def _spool_material(self, spool: dict[str, Any]) -> str | None:
        filament = spool.get("filament")
        filament = filament if isinstance(filament, dict) else {}
        material = str(filament.get("material") or "").strip().upper()
        return material or None

    def _track_hydration(
        self, now: float, humidity: float | None
    ) -> tuple[float | None, float | None]:
        """Accrue humidity dose on the active spool; return (dose, saturation)."""
        spool_id, spool = self._active_spool()
        if spool_id is None:
            return None, None
        material = self._spool_material(spool)
        record = self.spool_dose.setdefault(
            spool_id,
            {
                "dose_rh_h": 0.0,
                "tracked_hours": 0.0,
                "material": material,
                "first_seen": _iso(now),
                "last_dry_at": None,
            },
        )
        if material:
            record["material"] = material
        if self._dose_last_at is not None and humidity is not None:
            delta_h = (now - self._dose_last_at) / 3600
            if 0 < delta_h <= HUMIDITY_SAMPLE_GAP_MAX_S / 3600:
                record["dose_rh_h"] = round(
                    (_finite_number(record.get("dose_rh_h")) or 0.0)
                    + max(0.0, humidity - DRY_STORAGE_RH) * delta_h,
                    2,
                )
                record["tracked_hours"] = round(
                    (_finite_number(record.get("tracked_hours")) or 0.0) + delta_h,
                    2,
                )
                self._mark_dirty()
        self._dose_last_at = now
        if len(self.spool_dose) > SPOOL_DOSE_LIMIT:
            ordered = sorted(
                self.spool_dose,
                key=lambda key: str(self.spool_dose[key].get("first_seen")),
            )
            for oldest in ordered:
                if len(self.spool_dose) <= SPOOL_DOSE_LIMIT:
                    break
                if oldest != spool_id:
                    del self.spool_dose[oldest]
                    self._mark_dirty()
        dose = _finite_number(record.get("dose_rh_h")) or 0.0
        threshold = MOISTURE_THRESHOLD_RH_H.get(
            _material_key(material) or "", DEFAULT_MOISTURE_THRESHOLD
        )
        saturation = dose / threshold * 100 if threshold > 0 else None
        record["untracked"] = (
            _finite_number(record.get("tracked_hours")) or 0.0
        ) < SPOOL_UNTRACKED_HOURS
        return dose, saturation

    def mark_dried(self) -> bool:
        """Reset the active spool's hydration dose after a dry cycle."""
        spool_id, _spool = self._active_spool()
        if spool_id is None:
            return False
        record = self.spool_dose.setdefault(spool_id, {})
        record["dose_rh_h"] = 0.0
        record["last_dry_at"] = _iso(_now_ts())
        self._mark_dirty()
        return True

    # -- mass ledger -------------------------------------------------------------

    def record_mass(
        self, filename: str, expected_mm: float | None, reported_mm: float | None
    ) -> None:
        """Ledger a completed print: declared vs. reported filament mass."""
        expected = _finite_number(expected_mm)
        reported = _finite_number(reported_mm)
        if expected is None or reported is None or expected <= 0:
            return
        debt_pct = (reported - expected) / expected * 100
        self.mass_ledger.append(
            {
                "file": filename,
                "expected_mm": round(expected, 1),
                "reported_mm": round(reported, 1),
                "debt_pct": round(debt_pct, 2),
                "at": _iso(_now_ts()),
            }
        )
        self.debt_ema = (
            debt_pct
            if self.debt_ema is None
            else round(0.7 * self.debt_ema + 0.3 * debt_pct, 2)
        )
        self._mark_dirty()

    def _ledger_baseline(self) -> float | None:
        """Learned baseline: upper quartile of ledger debt once armed.

        Completed prints legitimately over-report (skirt, priming, purge), so
        the healthy baseline is the upper quartile — robust to a minority of
        drifting prints without letting drift redefine 'normal'.
        """
        if len(self.mass_ledger) < LEDGER_ARMED_PRINTS:
            return None
        debts = [
            entry["debt_pct"]
            for entry in self.mass_ledger
            if _finite_number(entry.get("debt_pct")) is not None
        ]
        if len(debts) < LEDGER_ARMED_PRINTS:
            return None
        debts.sort()
        return statistics.quantiles(debts, n=4)[2]

    def _ledger_drift(self) -> float | None:
        """Points the EMA sits below the learned baseline, or None."""
        baseline = self._ledger_baseline()
        if baseline is None or self.debt_ema is None:
            return None
        return baseline - self.debt_ema

    def _nozzle_wear_pct(self, material: str | None) -> float | None:
        """Peak-flow ceiling decline for the active material, in percent."""
        key = str(material or "unknown")
        peaks = self.analyzer.flow_peaks.get(key)
        if not isinstance(peaks, list) or len(peaks) < 4:
            return None
        baseline = statistics.median(peaks[:-1])
        if baseline <= 0:
            return None
        return max(0.0, (baseline - peaks[-1]) / baseline * 100)

    # -- forecast model -----------------------------------------------------------

    def _factor(
        self,
        key: str,
        points: float,
        detail: str,
        remedy: str = "",
        nogo: bool = False,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "points": round(points),
            "detail": detail,
            "remedy": remedy,
            "nogo": nogo,
        }

    def _moisture_factor(
        self,
        saturation: float | None,
        material: str | None,
        untracked: bool,
    ) -> dict[str, Any] | None:
        if saturation is None or material is None:
            return None
        if _material_key(material) is None and saturation < 50:
            return None
        points = min(25.0, max(0.0, saturation) * 0.25)
        if untracked:
            points /= 2
        if points < 1:
            return None
        note = " (dose still being tracked)" if untracked else ""
        return self._factor(
            "moisture",
            points,
            f"spool saturation ~{saturation:.0f}%{note}",
            "dry the spool and mark it dried",
        )

    def _file_history_factor(self, filename: str) -> dict[str, Any] | None:
        stats = self.analyzer.file_stats.get(filename)
        if not isinstance(stats, dict):
            return None
        attempts = int(stats.get("attempts") or 0)
        completed = int(stats.get("completed") or 0)
        faults = [f for f in stats.get("faults") or [] if f]
        failed = max(0, attempts - completed)
        if not faults and not failed:
            return None
        points = min(20.0, 6.0 * failed + 2.0 * len(set(faults)))
        return self._factor(
            "file_history",
            points,
            f"{filename} completed {completed}/{attempts} attempts",
            "inspect previous failure forensics before running",
        )

    def build_forecast(
        self,
        status: dict[str, Any],
        now: float,
        saturation: float | None,
        findings: list[dict[str, str]],
        filename: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Score the target file and assemble the Printcast payload."""
        data = self.coordinator.data or {}
        print_stats = status.get("print_stats") or {}
        state = str(print_stats.get("state") or "")
        live = state in ("printing", "paused")
        target = (
            filename
            or str(print_stats.get("filename") or "")
            or str((status.get("virtual_sdcard") or {}).get("file_path") or "")
        )
        meta = meta or {}
        filament_total = _finite_number(meta.get("filament_total"))
        file_type = str(meta.get("filament_type") or "").strip().upper() or None
        if filename is None:
            filament_total = filament_total or _finite_number(
                data.get("filament_total")
            )
            file_type = (
                file_type or str(data.get("filament_type") or "").upper() or None
            )
        material = (
            file_type
            or str(self.analyzer.metrics.get("material") or "")
            or str(self.analyzer.metrics.get("spool_material") or "")
        )

        factors: list[dict[str, Any]] = []
        labels = {str(f.get("label") or "") for f in findings}

        # Klippy readiness — hard gate.
        klippy = str((data.get("printer.info") or {}).get("state") or "unknown")
        if klippy not in ("ready", "startup"):
            factors.append(
                self._factor(
                    "klippy",
                    100,
                    f"klippy state is {klippy}",
                    "restart firmware before printing",
                    nogo=True,
                )
            )

        # Spool fit — hard gate when both figures are known.
        remaining = _finite_number(self.analyzer.metrics.get("spool_remaining_mm"))
        if (
            filament_total is not None
            and remaining is not None
            and filament_total > remaining
        ):
            factors.append(
                self._factor(
                    "spool_fit",
                    100,
                    f"file needs ~{filament_total / 1000:.1f}m, spool holds "
                    f"~{remaining / 1000:.1f}m",
                    "load a larger spool or splice mid-print",
                    nogo=True,
                )
            )

        # Material mismatch.
        spool_material = str(self.analyzer.metrics.get("spool_material") or "").upper()
        if (
            file_type
            and spool_material
            and file_type not in spool_material
            and spool_material not in file_type
        ):
            factors.append(
                self._factor(
                    "material_mismatch",
                    40,
                    f"file sliced for {file_type}, spool is {spool_material}",
                    "swap spool or re-slice for the loaded material",
                )
            )

        # Hydration dose.
        _spool_id, spool = self._active_spool()
        spool_record = self.spool_dose.get(_spool_id or "", {})
        moisture = self._moisture_factor(
            saturation,
            material or self._spool_material(spool),
            bool(spool_record.get("untracked")),
        )
        if moisture is not None:
            factors.append(moisture)

        # Mesh freshness and drift.
        mesh_age = _finite_number(
            (self.analyzer.metrics.get("preflight") or {}).get("mesh_age_days")
        )
        if mesh_age is not None and mesh_age > 14:
            factors.append(
                self._factor(
                    "mesh_age",
                    10,
                    f"bed mesh is {mesh_age:.0f} days old",
                    "re-probe the bed mesh",
                )
            )
        elif (self.analyzer.metrics.get("preflight") or {}).get("mesh_fresh") is False:
            factors.append(
                self._factor(
                    "mesh_age", 10, "bed mesh is stale", "re-probe the bed mesh"
                )
            )
        if labels & set(_MESH_DRIFT_FINDINGS):
            factors.append(
                self._factor(
                    "mesh_drift",
                    8,
                    "bed surface or tram drifted since last probe",
                    "re-probe the bed mesh",
                )
            )

        # File history (pre-print only — pointless once running).
        if not live and target:
            history = self._file_history_factor(target)
            if history is not None:
                factors.append(history)

        # Ambient envelope vs material profile.
        ambient = _finite_number(self.analyzer.metrics.get("ambient_c"))
        material_key = _material_key(material)
        if (
            ambient is not None
            and material_key in HYGROSCOPIC_MATERIALS
            and material_key not in ("TPU", "PETG")
            and ambient < 25
        ):
            factors.append(
                self._factor(
                    "ambient",
                    15,
                    f"chamber at {ambient:.0f}°C is cold for {material}",
                    "pre-heat the chamber before starting",
                )
            )

        # Extrusion debt drift.
        drift = self._ledger_drift()
        if drift is not None and drift > 0:
            factors.append(
                self._factor(
                    "extrusion_debt",
                    min(15.0, drift * 3),
                    f"extrusion runs {drift:.1f} pts below the learned baseline",
                    "inspect for a partial clog before a long job",
                )
            )

        # Nozzle wear: last peak-flow ceiling vs the learned median.
        wear = self._nozzle_wear_pct(material)
        if wear is not None and wear > 15:
            factors.append(
                self._factor(
                    "nozzle_wear",
                    8,
                    f"peak flow is {wear:.0f}% below its learned ceiling",
                    "consider a nozzle swap",
                )
            )

        # Recent config change.
        changed_at = self.analyzer.config_changed_at
        if changed_at:
            try:
                from datetime import datetime

                stamp = datetime.fromisoformat(str(changed_at)).timestamp()
                if now - stamp < 86400:
                    factors.append(
                        self._factor(
                            "config_changed",
                            5,
                            "printer config changed within the last day",
                            "review recent printer.cfg edits",
                        )
                    )
            except (TypeError, ValueError):
                pass

        # Active PSU/driver findings.
        for label in _RISK_FINDINGS:
            if label in labels:
                factors.append(
                    self._factor(
                        label.replace(" ", "_"),
                        10,
                        f"active finding: {label}",
                        "resolve the reported hardware finding first",
                    )
                )

        # Live twin drift replaces the pre-print-only factors' gap.
        if live:
            twin = _finite_number(self.analyzer.metrics.get("twin_drift_pct"))
            if twin is not None and twin > 5:
                factors.append(
                    self._factor(
                        "twin_drift",
                        min(20.0, twin),
                        f"running {twin:.0f}% off the golden run for this file",
                        "watch for an early failure signature",
                    )
                )

        score = max(0.0, 100.0 - sum(f["points"] for f in factors))
        nogo = any(f["nogo"] for f in factors)
        if nogo:
            verdict = "NO-GO"
        elif score >= VERDICT_CLEAR:
            verdict = "CLEAR"
        elif score >= VERDICT_CAUTION:
            verdict = "CAUTION"
        elif score >= VERDICT_POOR:
            verdict = "POOR"
        else:
            verdict = "NO-GO"

        top = max(
            (f for f in factors if f.get("remedy") and not f["nogo"]),
            key=lambda f: f["points"],
            default=None,
        )
        recommendation = (
            f"{top['remedy']} → +{top['points']} pts" if top is not None else None
        )
        partial = filament_total is None and not live
        return {
            "filename": target or None,
            "mode": _LIVE_ONLY_LABEL if live else "forecast",
            "score": round(score),
            "verdict": verdict,
            "factors": factors,
            "recommendation": recommendation,
            "partial": partial,
            "computed_at": _iso(now),
        }

    # -- main pass ----------------------------------------------------------------

    def analyze(
        self, status: dict[str, Any], now: float, findings: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Update dose, ledger metrics, and the forecast; return new findings."""
        metrics = self.analyzer.metrics
        humidity = self._humidity_pct(status)
        dose, saturation = self._track_hydration(now, humidity)
        metrics["humidity_pct"] = round(humidity, 1) if humidity is not None else None
        metrics["spool_hydration_dose_rh_h"] = dose
        metrics["spool_saturation_pct"] = (
            round(saturation, 1) if saturation is not None else None
        )
        metrics["extrusion_debt_pct"] = self.debt_ema
        metrics["mass_ledger_entries"] = len(self.mass_ledger)
        drift = self._ledger_drift()
        metrics["extrusion_debt_drift_pts"] = (
            round(drift, 1) if drift is not None else None
        )

        out: list[dict[str, str]] = []
        material = str(metrics.get("material") or metrics.get("spool_material") or "")
        if (
            saturation is not None
            and saturation > MOISTURE_WARN_SATURATION_PCT
            and _material_key(material) in HYGROSCOPIC_MATERIALS
        ):
            print_stats = status.get("print_stats") or {}
            queue = (self.coordinator.data or {}).get("queue") or {}
            if print_stats.get("state") in ("printing", "paused") or queue.get(
                "queued_jobs"
            ):
                out.append(
                    {
                        "severity": "warn",
                        "label": "filament moisture risk",
                        "detail": (
                            f"the active {material or 'spool'} is "
                            f"~{saturation:.0f}% saturated — wet filament "
                            "causes stringing, popping, and weak layers"
                        ),
                    }
                )
        if drift is not None and drift > LEDGER_DRIFT_PTS:
            out.append(
                {
                    "severity": "warn",
                    "label": "extrusion drift",
                    "detail": (
                        f"reported extrusion is {drift:.1f} pts below the "
                        "learned mass baseline — early partial-clog signature"
                    ),
                }
            )

        forecast = self.build_forecast(status, now, saturation, findings + out)
        self.forecast = forecast
        metrics["printability_score"] = forecast["score"]
        metrics["printability_verdict"] = forecast["verdict"]
        metrics["printability_factors"] = forecast["factors"]
        metrics["printability_recommendation"] = forecast["recommendation"]
        metrics["printcast_filename"] = forecast["filename"]
        metrics["printcast_mode"] = forecast["mode"]

        self._maybe_announce(status, forecast)
        return out

    # -- file-select announcement --------------------------------------------------

    def _maybe_announce(self, status: dict[str, Any], forecast: dict[str, Any]) -> None:
        """Announce a forecast when the selected file changes while idle."""
        print_stats = status.get("print_stats") or {}
        if print_stats.get("state") != "standby":
            return
        selected = str((status.get("virtual_sdcard") or {}).get("file_path") or "")
        if not selected or selected == self._last_selected:
            return
        self._last_selected = selected
        last_verdict = self._last_announced.get(selected)
        announce = forecast["score"] < VERDICT_CLEAR or (
            last_verdict is not None and last_verdict != forecast["verdict"]
        )
        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_PRINTCAST}_{self.coordinator.config_entry.entry_id}",
            dict(forecast),
        )
        if not announce:
            return
        self._last_announced[selected] = forecast["verdict"]
        self._mark_dirty()
        if not self.analyzer.notify_service:
            return
        factors = "; ".join(f["detail"] for f in forecast["factors"][:3])
        message = (
            f"Printcast {forecast['score']}/100 ({forecast['verdict']}): "
            f"{selected.split('/')[-1]}" + (f" — {factors}" if factors else "")
        )
        self.hass.async_create_task(
            self.analyzer._async_notify(  # noqa: SLF001 - shared notify helper
                {"title": "Printcast forecast", "message": message}
            )
        )


def _now_ts() -> float:
    """Return the current UNIX timestamp."""
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).timestamp()
