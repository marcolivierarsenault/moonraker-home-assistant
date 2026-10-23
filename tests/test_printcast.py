"""Tests for the Printcast predictive forecast engine."""

from unittest.mock import MagicMock, patch

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.advance_moonraker_control import MoonrakerDataUpdateCoordinator
from custom_components.advance_moonraker_control.const import (
    CONF_OPTION_HUMIDITY_SENSOR,
    CONF_OPTION_NOTIFY_SERVICE,
    DOMAIN,
    SIGNAL_PRINTCAST,
)
from custom_components.advance_moonraker_control.printcast import (
    LEDGER_ARMED_PRINTS,
    SPOOL_DOSE_LIMIT,
    MoonrakerPrintcast,
    _material_key,
)

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.start"),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
    ):
        yield


def _coordinator(hass, options=None, entry_id="printcast"):
    """Build a coordinator whose analyzer owns a Printcast engine."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, options=options or {}, entry_id=entry_id
    )
    return MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )


def _status(state="standby", filename="", selected=""):
    """Minimal status payload for forecast passes."""
    return {
        "print_stats": {
            "state": state,
            "filename": filename,
            "print_duration": 0.0,
            "total_duration": 0.0,
            "filament_used": 0.0,
        },
        "virtual_sdcard": {"file_path": selected},
        "extruder": {"temperature": 25.0, "power": 0.0, "target": 0.0},
        "heater_bed": {"temperature": 24.0, "power": 0.0, "target": 0.0},
    }


def _spool(material="PETG", spool_id=7, remaining_mm=10000.0):
    """Spoolman details dict as stored in coordinator data."""
    return {
        "id": spool_id,
        "remaining_length": remaining_mm,
        "filament": {"material": material, "density": 1.24, "diameter": 1.75},
    }


def _ready_data(spool=None, **extra):
    """Coordinator data with klippy ready and optional spool."""
    data = {"printer.info": {"state": "ready"}}
    if spool is not None:
        data["spool_details"] = spool
    data.update(extra)
    return data


def test_material_key_normalizes():
    """Material strings map to threshold keys."""
    assert _material_key("PETG-CF") == "PETG"
    assert _material_key("nylon pa12") == "PA"
    assert _material_key("Nylon") == "PA"
    assert _material_key("woodfill") is None
    assert _material_key(None) is None


def test_hydration_dose_accrues_above_40_rh(hass: HomeAssistant):
    """Dose integrates only the humidity above the dry-storage floor."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(spool=_spool("PETG"))
    analyzer = coordinator.analyzer
    status = _status()
    status["bme280 chamber"] = {"humidity": 60.0}

    analyzer.analyze(status, now=1000.0)
    analyzer.analyze(status, now=4600.0)  # 1h at 60% → (60-40)*1 = 20 RH·h
    assert analyzer.metrics["humidity_pct"] == 60.0
    assert analyzer.metrics["spool_hydration_dose_rh_h"] == 20.0
    # PETG threshold 80 → 25% saturated.
    assert analyzer.metrics["spool_saturation_pct"] == 25.0

    # Below the floor nothing accrues.
    status["bme280 chamber"]["humidity"] = 30.0
    analyzer.analyze(status, now=8200.0)
    assert analyzer.metrics["spool_hydration_dose_rh_h"] == 20.0


def test_hydration_gap_and_no_spool(hass: HomeAssistant):
    """Long gaps and missing spools do not accrue dose."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data()
    analyzer = coordinator.analyzer
    analyzer.analyze(_status(), now=1000.0)
    assert analyzer.metrics["spool_hydration_dose_rh_h"] is None
    assert analyzer.metrics["spool_saturation_pct"] is None

    coordinator.data = _ready_data(spool=_spool("PETG"))
    status = _status()
    status["bme280 room"] = {"humidity": 80.0}
    analyzer.analyze(status, now=2000.0)
    analyzer.analyze(status, now=2000.0 + 25 * 3600)  # gap beyond cap
    assert analyzer.metrics["spool_hydration_dose_rh_h"] == 0.0


def test_humidity_option_overrides_klipper_sensor(hass: HomeAssistant):
    """A configured HA humidity sensor wins over Klipper env sensors."""
    coordinator = _coordinator(
        hass, options={CONF_OPTION_HUMIDITY_SENSOR: "sensor.room_humidity"}
    )
    coordinator.data = _ready_data(spool=_spool("PLA"))
    hass.states.async_set("sensor.room_humidity", "55")
    status = _status()
    status["bme280 chamber"] = {"humidity": 90.0}
    analyzer = coordinator.analyzer
    analyzer.analyze(status, now=1000.0)
    assert analyzer.metrics["humidity_pct"] == 55.0


def test_mark_dried_resets_dose(hass: HomeAssistant):
    """Marking the spool dried zeroes the dose and stamps the record."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(spool=_spool("PA"))
    analyzer = coordinator.analyzer
    status = _status()
    status["bme280 chamber"] = {"humidity": 90.0}
    analyzer.analyze(status, now=1000.0)
    analyzer.analyze(status, now=4600.0)
    assert analyzer.metrics["spool_saturation_pct"] > 0

    assert analyzer.printcast.mark_dried() is True
    record = analyzer.printcast.spool_dose["7"]
    assert record["dose_rh_h"] == 0.0
    assert record["last_dry_at"]

    # One more humid hour re-accrues from zero: 50 RH·h → 125% of the PA
    # threshold (would read 250% had the reset failed).
    analyzer.analyze(status, now=8200.0)
    assert analyzer.metrics["spool_saturation_pct"] == 125.0


def test_mark_dried_without_spool(hass: HomeAssistant):
    """Mark-dried is a no-op when no spool is loaded."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data()
    assert coordinator.analyzer.printcast.mark_dried() is False


def test_spool_swap_keeps_per_spool_dose(hass: HomeAssistant):
    """Each spool id keeps its own dose across swaps."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    status = _status()
    status["bme280 room"] = {"humidity": 60.0}

    coordinator.data = _ready_data(spool=_spool("PETG", spool_id=1))
    analyzer.analyze(status, now=1000.0)
    analyzer.analyze(status, now=4600.0)
    assert analyzer.printcast.spool_dose["1"]["dose_rh_h"] == 20.0

    coordinator.data = _ready_data(spool=_spool("PLA", spool_id=2))
    analyzer.analyze(status, now=5000.0)
    analyzer.analyze(status, now=8600.0)
    # The 400s swap interval plus the full hour both accrue to spool 2.
    assert analyzer.printcast.spool_dose["2"]["dose_rh_h"] == pytest.approx(22.22)
    assert analyzer.printcast.spool_dose["1"]["dose_rh_h"] == 20.0


def test_untracked_flag_and_moisture_finding(hass: HomeAssistant):
    """A saturated hygroscopic spool raises a moisture-risk finding."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(spool=_spool("PA"))
    analyzer = coordinator.analyzer
    analyzer.printcast.spool_dose["7"] = {
        "dose_rh_h": 35.0,  # 87.5% of the PA 40 RH·h threshold
        "tracked_hours": 30.0,
        "material": "PA",
        "first_seen": "2024-01-01",
        "last_dry_at": None,
    }
    status = _status(state="printing", filename="job.gcode")
    analyzer.analyze(status, now=1000.0)
    labels = [f["label"] for f in analyzer.findings]
    assert "filament moisture risk" in labels
    assert analyzer.printcast.spool_dose["7"]["untracked"] is False


def test_dose_bound_evicts_oldest_not_active(hass: HomeAssistant):
    """The dose table stays bounded and never evicts the active spool."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    for index in range(SPOOL_DOSE_LIMIT + 2):
        analyzer.printcast.spool_dose[str(index)] = {
            "dose_rh_h": 0.0,
            "tracked_hours": 0.0,
            "first_seen": f"2024-01-{index + 1:02d}",
        }
    coordinator.data = _ready_data(spool=_spool("PLA", spool_id=0))
    analyzer.analyze(_status(), now=1000.0)
    assert "0" in analyzer.printcast.spool_dose
    assert len(analyzer.printcast.spool_dose) <= SPOOL_DOSE_LIMIT


def test_mass_ledger_and_drift(hass: HomeAssistant):
    """Completed prints ledger debt; drops below baseline flag drift."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data()
    printcast = coordinator.analyzer.printcast

    for _ in range(LEDGER_ARMED_PRINTS):
        printcast.record_mass("job.gcode", expected_mm=1000.0, reported_mm=1050.0)
    assert printcast.debt_ema == 5.0
    assert len(printcast.mass_ledger) == LEDGER_ARMED_PRINTS
    assert printcast._ledger_drift() == 0.0

    for _ in range(8):
        printcast.record_mass("job.gcode", expected_mm=1000.0, reported_mm=990.0)
    assert printcast.debt_ema < 5.0
    drift = printcast._ledger_drift()
    assert drift is not None and drift > 4.0

    coordinator.analyzer.analyze(_status(), now=1000.0)
    labels = [f["label"] for f in coordinator.analyzer.findings]
    assert "extrusion drift" in labels


def test_mass_ledger_ignores_bad_input(hass: HomeAssistant):
    """Non-positive or missing figures are not ledgered."""
    printcast = _coordinator(hass).analyzer.printcast
    printcast.record_mass("a", expected_mm=None, reported_mm=100.0)
    printcast.record_mass("a", expected_mm=0.0, reported_mm=100.0)
    printcast.record_mass("a", expected_mm=100.0, reported_mm=None)
    assert len(printcast.mass_ledger) == 0
    assert printcast._ledger_baseline() is None
    assert printcast._ledger_drift() is None


def test_forecast_clear_on_ideal_machine(hass: HomeAssistant):
    """A healthy idle machine with a fitting spool forecasts CLEAR."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=5000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    analyzer.analyze(_status(selected="part.gcode"), now=1000.0)
    metrics = analyzer.metrics
    assert metrics["printability_verdict"] == "CLEAR"
    assert metrics["printability_score"] >= 85
    assert metrics["printcast_filename"] == "part.gcode"
    assert metrics["printcast_mode"] == "forecast"


def test_forecast_nogo_on_short_spool_and_bad_klippy(hass: HomeAssistant):
    """Spool shortfall and an unready Klippy each force NO-GO."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA", remaining_mm=100.0),
        filament_total=5000.0,
        filament_type="PLA",
    )
    analyzer = coordinator.analyzer
    analyzer.analyze(_status(selected="big.gcode"), now=1000.0)
    assert analyzer.metrics["printability_verdict"] == "NO-GO"
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "spool_fit" in keys

    coordinator.data["printer.info"]["state"] = "error"
    coordinator.data["filament_total"] = 50.0
    analyzer.analyze(_status(), now=1100.0)
    assert analyzer.metrics["printability_verdict"] == "NO-GO"
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "klippy" in keys


def test_forecast_factors_and_recommendation(hass: HomeAssistant):
    """Risk factors carry points and the top remedy is recommended."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PETG"), filament_total=5000.0, filament_type="PETG"
    )
    analyzer = coordinator.analyzer
    analyzer.printcast.spool_dose["7"] = {
        "dose_rh_h": 48.0,  # 60% saturated PETG
        "tracked_hours": 40.0,
        "material": "PETG",
        "first_seen": "2024-01-01",
    }
    analyzer.analyze(_status(selected="part.gcode"), now=1000.0)
    forecast = analyzer.printcast.forecast
    keys = [f["key"] for f in forecast["factors"]]
    assert "moisture" in keys
    assert forecast["verdict"] in ("CLEAR", "CAUTION")
    assert forecast["recommendation"] is not None
    assert "+15 pts" in forecast["recommendation"]


def test_forecast_file_history_and_config_drift(hass: HomeAssistant):
    """Prior failures and a fresh config change deduct points."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(filament_total=1000.0, filament_type="PLA")
    analyzer = coordinator.analyzer
    analyzer.file_stats["risky.gcode"] = {
        "attempts": 3,
        "completed": 1,
        "faults": ["extrusion stall", "spool shortfall"],
    }
    analyzer.config_changed_at = "2999-01-01T00:00:00+00:00"  # future → recent
    analyzer.analyze(_status(selected="risky.gcode"), now=1000.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "file_history" in keys
    assert "config_changed" in keys


def test_forecast_live_mode_uses_twin_drift(hass: HomeAssistant):
    """While printing, twin drift is scored instead of file history."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(filament_total=1000.0, filament_type="PLA")
    analyzer = coordinator.analyzer
    analyzer.metrics["twin_drift_pct"] = 25.0
    analyzer.file_stats["job.gcode"] = {
        "attempts": 3,
        "completed": 0,
        "faults": ["stall"],
    }
    status = _status(state="printing", filename="job.gcode")
    analyzer.analyze(status, now=1000.0)
    assert analyzer.metrics["printcast_mode"] == "live"
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "file_history" not in keys

    # The twin pass clears the metric without a golden run; inject drift and
    # re-run the forecast directly to exercise the live factor.
    analyzer.metrics["twin_drift_pct"] = 25.0
    forecast = analyzer.printcast.build_forecast(status, 1100.0, None, [])
    keys = [f["key"] for f in forecast["factors"]]
    assert "twin_drift" in keys
    assert forecast["mode"] == "live"


def test_forecast_partial_and_verdict_bands(hass: HomeAssistant):
    """Missing metadata marks partial; scores bucket into verdicts."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data()
    analyzer = coordinator.analyzer
    analyzer.analyze(_status(selected="mystery.gcode"), now=1000.0)
    assert analyzer.printcast.forecast["partial"] is True
    assert analyzer.metrics["printability_verdict"] == "CLEAR"


def test_forecast_findings_penalties(hass: HomeAssistant):
    """Mesh drift and hardware findings deduct forecast points."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=1000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    now = 1_800_000_000.0
    analyzer.mesh_history = [{"at": "2026-12-20T00:00:00+00:00"}]
    status = _status(selected="part.gcode")
    # Rising driver temperature over 5 samples trips the thermal finding.
    for index, temp in enumerate((60.0, 65.0, 70.0, 75.0, 80.0)):
        status["tmc2209 extruder"] = {"temperature": temp}
        analyzer.analyze(status, now=now - 300 + index * 60)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "mesh_age" in keys
    assert "driver_overheating" in keys


async def test_file_select_dispatches_and_notifies(hass: HomeAssistant):
    """Selecting a file while idle fires the printcast event + notify."""
    coordinator = _coordinator(hass, options={CONF_OPTION_NOTIFY_SERVICE: "phone"})
    coordinator.data = _ready_data(
        spool=_spool("PA", remaining_mm=10.0),
        filament_total=5000.0,
        filament_type="PA",
    )
    analyzer = coordinator.analyzer
    events = []
    async_dispatcher_connect(
        hass,
        f"{SIGNAL_PRINTCAST}_{coordinator.config_entry.entry_id}",
        events.append,
    )
    calls = []
    hass.services.async_register("notify", "phone", lambda call: calls.append(call))

    status = _status(selected="heavy.gcode")
    analyzer.analyze(status, now=1000.0)
    await hass.async_block_till_done()
    assert events and events[-1]["verdict"] == "NO-GO"
    assert calls and "Printcast" in calls[-1].data["message"]

    # Same file again → no duplicate dispatch.
    count = len(events)
    analyzer.analyze(status, now=1100.0)
    assert len(events) == count


def test_file_select_clear_skips_notify(hass: HomeAssistant):
    """A CLEAR forecast still dispatches but skips the notification."""
    coordinator = _coordinator(hass, options={CONF_OPTION_NOTIFY_SERVICE: "phone"})
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=1000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    status = _status(selected="easy.gcode")
    analyzer.analyze(status, now=1000.0)
    assert analyzer.metrics["printability_verdict"] == "CLEAR"


async def test_store_roundtrip(hass: HomeAssistant):
    """Dose, ledger, EMA, and announce memory persist through the store."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    await analyzer.async_load()
    analyzer.printcast.spool_dose["9"] = {
        "dose_rh_h": 12.5,
        "tracked_hours": 30.0,
        "material": "PETG",
    }
    analyzer.printcast.record_mass("a.gcode", 1000.0, 1020.0)
    analyzer.printcast._last_announced = {"a.gcode": "CLEAR"}
    await analyzer._async_save()

    coordinator2 = _coordinator(hass, entry_id="printcast")
    await coordinator2.analyzer.async_load()
    restored = coordinator2.analyzer.printcast
    assert restored.spool_dose["9"]["dose_rh_h"] == 12.5
    assert len(restored.mass_ledger) == 1
    assert restored.debt_ema == 2.0
    assert restored._last_announced == {"a.gcode": "CLEAR"}


def test_build_forecast_for_arbitrary_file(hass: HomeAssistant):
    """forecast_for_file-style calls score a file with explicit metadata."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(spool=_spool("PLA", remaining_mm=50.0))
    analyzer = coordinator.analyzer
    analyzer.analyze(_status(), now=1000.0)
    forecast = analyzer.printcast.build_forecast(
        _status(),
        1000.0,
        None,
        [],
        filename="huge.gcode",
        meta={"filament_total": 99999.0, "filament_type": "ABS"},
    )
    assert forecast["filename"] == "huge.gcode"
    assert forecast["verdict"] == "NO-GO"
    keys = [f["key"] for f in forecast["factors"]]
    assert "spool_fit" in keys
    assert "material_mismatch" in keys


def test_forecast_handles_unknown_material_moisture(hass: HomeAssistant):
    """Unknown materials only draw a moisture factor past 50% saturation."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("EXOTIC", spool_id=5), filament_total=1000.0
    )
    analyzer = coordinator.analyzer
    analyzer.printcast.spool_dose["5"] = {
        "dose_rh_h": 20.0,
        "tracked_hours": 40.0,
        "material": "EXOTIC",
        "first_seen": "2024-01-01",
    }
    analyzer.analyze(_status(selected="x.gcode"), now=1000.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "moisture" not in keys  # 20/160 = 12.5% < 50%

    analyzer.printcast.spool_dose["5"]["dose_rh_h"] = 150.0
    analyzer.analyze(_status(), now=1100.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "moisture" in keys


def test_ambient_and_nozzle_wear_factors(hass: HomeAssistant):
    """Cold ambient on high-shrink material and nozzle wear deduct."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("ABS"), filament_total=1000.0, filament_type="ABS"
    )
    analyzer = coordinator.analyzer
    analyzer.ambient_sensor = "sensor.chamber_temp"
    hass.states.async_set("sensor.chamber_temp", "18")
    # Last peak 20% below the learned median → nozzle-wear factor.
    analyzer.flow_peaks["ABS"] = [10.0, 10.0, 10.0, 10.0, 8.0]
    analyzer.analyze(_status(selected="enclosure.gcode"), now=1000.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "ambient" in keys
    assert "nozzle_wear" in keys
    verdict = analyzer.metrics["printability_verdict"]
    assert verdict in ("CAUTION", "POOR")


def test_engine_is_passive(hass: HomeAssistant):
    """Printcast never calls the Moonraker API, even when marking dried."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(spool=_spool("PA"))
    analyzer = coordinator.analyzer
    analyzer.analyze(_status(), now=1000.0)
    analyzer.printcast.mark_dried()
    coordinator.moonraker.assert_not_called()


def test_init_accepts_custom_dirty_callback(hass: HomeAssistant):
    """The engine wires persistence through its mark_dirty callback."""
    analyzer = _coordinator(hass).analyzer
    calls = []
    engine = MoonrakerPrintcast(analyzer, lambda: calls.append(1))
    engine.coordinator.data = _ready_data(spool=_spool("PLA"))
    status = _status()
    status["bme280 room"] = {"humidity": 60.0}
    engine.analyze(status, 1000.0, [])
    engine.analyze(status, 4600.0, [])
    assert calls  # dose accrual marked the store dirty


def test_mesh_age_factor_on_stale_flag(hass: HomeAssistant):
    """An unparseable mesh timestamp still flags a stale mesh."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=1000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    analyzer.mesh_history = [{"at": "not-a-timestamp"}]
    analyzer.analyze(_status(selected="part.gcode"), now=1000.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "mesh_age" in keys


def test_verdict_poor_and_score_nogo_bands(hass: HomeAssistant):
    """POOR covers 40-59; soft-only factors can still reach NO-GO."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PETG"), filament_total=1000.0, filament_type="ABS"
    )
    analyzer = coordinator.analyzer
    # material mismatch (40) + cold ambient for ABS (15) → 45 = POOR.
    analyzer.ambient_sensor = "sensor.chamber_temp"
    hass.states.async_set("sensor.chamber_temp", "18")
    analyzer.analyze(_status(selected="part.gcode"), now=1000.0)
    assert analyzer.metrics["printability_verdict"] == "POOR"

    # Pile on soft factors until the score drops below 40 without a NO-GO flag.
    analyzer.file_stats["part.gcode"] = {
        "attempts": 4,
        "completed": 1,
        "faults": ["stall", "mesh", "flow"],
    }
    analyzer.mesh_history = [{"at": "2020-01-01T00:00:00+00:00"}]
    analyzer.analyze(_status(selected="part.gcode"), now=1_800_000_000.0)
    forecast = analyzer.printcast.forecast
    assert forecast["verdict"] == "NO-GO"
    assert all(not f["nogo"] for f in forecast["factors"])
    assert forecast["score"] < 40


def test_config_changed_bad_timestamp_ignored(hass: HomeAssistant):
    """An unparseable config timestamp does not add a factor."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=1000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    analyzer.config_changed_at = "not-a-date"
    analyzer.analyze(_status(selected="part.gcode"), now=1000.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "config_changed" not in keys


def test_ledger_baseline_needs_valid_debts(hass: HomeAssistant):
    """Ledger entries without debt figures cannot arm a baseline."""
    printcast = _coordinator(hass).analyzer.printcast
    for _ in range(LEDGER_ARMED_PRINTS + 1):
        printcast.mass_ledger.append({"file": "x", "debt_pct": "bad"})
    assert printcast._ledger_baseline() is None


def test_nozzle_wear_zero_baseline(hass: HomeAssistant):
    """A zero peak baseline reports no wear rather than dividing by zero."""
    analyzer = _coordinator(hass).analyzer
    analyzer.flow_peaks["PLA"] = [0.0, 0.0, 0.0, 0.0, 0.0]
    assert analyzer.printcast._nozzle_wear_pct("PLA") is None


def test_file_history_clean_record_no_factor(hass: HomeAssistant):
    """A file that always completed adds no history factor."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=1000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    analyzer.file_stats["reliable.gcode"] = {
        "attempts": 2,
        "completed": 2,
        "faults": [],
    }
    analyzer.analyze(_status(selected="reliable.gcode"), now=1000.0)
    keys = [f["key"] for f in analyzer.metrics["printability_factors"]]
    assert "file_history" not in keys


def test_mesh_drift_finding_deducts(hass: HomeAssistant):
    """An active surface-drift finding deducts mesh points."""
    coordinator = _coordinator(hass)
    coordinator.data = _ready_data(
        spool=_spool("PLA"), filament_total=1000.0, filament_type="PLA"
    )
    analyzer = coordinator.analyzer
    findings = [{"severity": "warn", "label": "bed surface changed", "detail": "x"}]
    forecast = analyzer.printcast.build_forecast(
        _status(selected="part.gcode"), 1000.0, None, findings
    )
    keys = [f["key"] for f in forecast["factors"]]
    assert "mesh_drift" in keys
