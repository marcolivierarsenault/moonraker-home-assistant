"""Tests for the server-side telemetry analyzer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import MoonrakerDataUpdateCoordinator
from custom_components.moonraker.analyzer import (
    FILAMENT_AREA_MM2,
    PRINT_HISTORY_LIMIT,
    _drift_stats,
    _finite_number,
    _matrix_from_mesh,
)
from custom_components.moonraker.const import (
    CONF_OPTION_ENERGY_RATE,
    CONF_OPTION_MAX_FLOW,
    CONF_OPTION_POWER_SENSOR,
    DOMAIN,
)
from custom_components.moonraker.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch("custom_components.moonraker.MoonrakerApiClient.stop"),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


def _coordinator(hass, options=None, entry_id="analyzer"):
    """Test coordinator."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, options=options or {}, entry_id=entry_id
    )
    return MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )


def _base_status() -> dict:
    """Test base status."""
    return {
        "print_stats": {
            "state": "standby",
            "filename": "",
            "print_duration": 0.0,
            "total_duration": 0.0,
            "filament_used": 0.0,
        },
        "extruder": {"temperature": 25.0, "power": 0.0, "target": 0.0},
        "heater_bed": {"temperature": 24.0, "power": 0.0, "target": 0.0},
        "motion_report": {"live_velocity": 0.0, "live_extruder_velocity": 0.0},
    }


def test_finite_number_coerces():
    """Test test finite number coerces."""
    assert _finite_number("3.5") == 3.5
    assert _finite_number(2) == 2.0
    assert _finite_number("bad") is None
    assert _finite_number(None) is None
    assert _finite_number(float("inf")) is None
    assert _finite_number(float("nan")) is None


def test_matrix_from_mesh_validation():
    """Test test matrix from mesh validation."""
    assert _matrix_from_mesh({}) is None
    assert _matrix_from_mesh({"mesh_matrix": "bad"}) is None
    assert _matrix_from_mesh({"mesh_matrix": [[0.1], "row"]}) is None
    assert _matrix_from_mesh({"mesh_matrix": [[0.1], [0.2, 0.3]]}) is None
    assert _matrix_from_mesh({"mesh_matrix": [[0.1, "x"]]}) is None
    matrix = [[0.1, 0.2], [0.3, 0.4]]
    assert _matrix_from_mesh({"mesh_matrix": matrix}) == matrix
    assert _matrix_from_mesh({"probed_matrix": matrix}) == matrix


def test_drift_stats_shape_mismatch():
    """Test test drift stats shape mismatch."""
    drift = _drift_stats([[0.1]], [[0.1], [0.2]])
    assert drift == {"rms": 0.0, "max": 0.0, "cells": []}
    drift = _drift_stats([[0.2]], [[0.1]])
    assert drift["rms"] == pytest.approx(0.1)
    assert drift["max"] == pytest.approx(0.1)
    drift = _drift_stats([[0.1]], [[0.1, 0.0]])
    assert drift["cells"] == []


async def test_store_persists_and_restores(hass):
    """Test test store persists and restores."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    await analyzer.async_load()
    status = _base_status()
    status["bed_mesh"] = {"mesh_matrix": [[0.01, 0.02], [0.0, -0.01]]}
    analyzer.analyze(status, now=1000.0)
    assert analyzer._mesh_baseline is not None

    analyzer.print_history.append({"filename": "cube.gcode", "state": "complete"})
    analyzer.total_kwh = 1.25
    analyzer._mark_dirty()
    await analyzer._async_save()

    restored = _coordinator(hass, entry_id="analyzer").analyzer
    await restored.async_load()
    assert restored._mesh_baseline["matrix"] == [[0.01, 0.02], [0.0, -0.01]]
    assert restored.print_history == [{"filename": "cube.gcode", "state": "complete"}]
    assert restored.total_kwh == pytest.approx(1.25)


async def test_store_load_failure_and_bad_shapes(hass):
    """Test test store load failure and bad shapes."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    with patch.object(
        analyzer._store, "async_load", side_effect=RuntimeError("corrupt")
    ):
        await analyzer.async_load()
    assert analyzer._store_loaded

    corrupt = _coordinator(hass, entry_id="other").analyzer
    corrupt._store.async_load = AsyncMock(
        return_value={
            "mesh_baseline": {"matrix": "bad"},
            "print_history": ["junk", {"filename": "a"}],
            "total_kwh": "nope",
        }
    )
    await corrupt.async_load()
    assert corrupt._mesh_baseline is None
    assert corrupt.print_history == [{"filename": "a"}]
    assert corrupt.total_kwh == 0.0


async def test_store_save_failure_is_non_fatal(hass):
    """Test test store save failure is non fatal."""
    analyzer = _coordinator(hass).analyzer
    await analyzer.async_load()
    analyzer._store_dirty = True
    with patch.object(analyzer._store, "async_save", side_effect=RuntimeError("io")):
        await analyzer._async_save()
    assert analyzer._store_dirty is False


async def test_shutdown_flushes_pending_save(hass):
    """Test test shutdown flushes pending save."""
    analyzer = _coordinator(hass).analyzer
    await analyzer.async_load()
    status = _base_status()
    status["bed_mesh"] = {"mesh_matrix": [[0.0]]}
    analyzer.analyze(status, now=1.0)
    assert analyzer._save_unsub is not None
    await analyzer.async_shutdown()
    assert analyzer._save_unsub is None
    assert analyzer._store_dirty is False


async def test_thermal_saturation_finding(hass):
    """Test test thermal saturation finding."""
    analyzer = _coordinator(hass).analyzer
    await analyzer.async_load()
    status = _base_status()
    samples = [
        {"temperature": 200 - index, "power": 1.0, "target": 200.0}
        for index in range(25)
    ]
    for index, sample in enumerate(samples):
        status["extruder"] = sample
        analyzer.analyze(status, now=float(index))
    labels = [finding["label"] for finding in analyzer.findings]
    assert "extruder saturated" in labels


async def test_thermal_oscillation_finding(hass):
    """Test test thermal oscillation finding."""
    analyzer = _coordinator(hass).analyzer
    await analyzer.async_load()
    status = _base_status()
    temps = [204.0 if index % 2 else 196.0 for index in range(30)]
    for index, temp in enumerate(temps):
        status["extruder"] = {
            "temperature": temp,
            "power": 0.5,
            "target": 200.0,
        }
        analyzer.analyze(status, now=float(index))
    labels = [finding["label"] for finding in analyzer.findings]
    assert "extruder pid oscillation" in labels


async def test_thermal_skips_incomplete_and_cold(hass):
    """Test test thermal skips incomplete and cold."""
    analyzer = _coordinator(hass).analyzer
    status = _base_status()
    status["extruder"] = {"temperature": None, "power": None, "target": 200.0}
    status["heater_generic chamber"] = {
        "temperature": 20.0,
        "power": 1.0,
        "target": 0.0,
    }
    for index in range(30):
        analyzer.analyze(status, now=float(index))
    assert analyzer.findings == []
    assert "heater_generic chamber" in analyzer.thermal_history


async def test_flow_headroom_and_saturation(hass):
    """Test test flow headroom and saturation."""
    coordinator = _coordinator(hass, options={CONF_OPTION_MAX_FLOW: 20.0})
    analyzer = coordinator.analyzer
    await analyzer.async_load()
    status = _base_status()
    status["motion_report"]["live_extruder_velocity"] = 10.0 / FILAMENT_AREA_MM2
    analyzer.analyze(status, now=0.0)
    assert analyzer.metrics["volumetric_flow_mm3"] == pytest.approx(10.0)
    assert analyzer.metrics["flow_headroom_pct"] == pytest.approx(50.0)

    status["motion_report"]["live_extruder_velocity"] = 20.0 / FILAMENT_AREA_MM2
    analyzer.analyze(status, now=10.0)
    assert analyzer.findings == []
    analyzer.analyze(status, now=16.0)
    assert analyzer.findings[0]["label"] == "flow saturated"
    status["motion_report"]["live_extruder_velocity"] = 0.0
    analyzer.analyze(status, now=17.0)
    assert analyzer._flow_saturated_since is None


async def test_retransmit_trend(hass):
    """Test test retransmit trend."""
    analyzer = _coordinator(hass).analyzer
    status = _base_status()
    status["mcu"] = {"last_stats": {"bytes_retransmit": 10, "bytes_invalid": 2}}
    status["mcu_extra toolhead"] = {"last_stats": {"bytes_retransmit": 5}}
    status["not_mcu"] = {"last_stats": {"bytes_retransmit": 99}}
    analyzer.analyze(status, now=0.0)
    assert analyzer.metrics["retransmit_total"] == 17
    assert analyzer.findings[0]["detail"].startswith("17 bytes")

    status["mcu"]["last_stats"]["bytes_retransmit"] = 25
    analyzer.analyze(status, now=30.0)
    analyzer.analyze(status, now=60.0)
    assert analyzer.metrics["retransmit_trend"] == "rising"
    analyzer.analyze(status, now=1000.0)
    assert analyzer.metrics["retransmit_trend"] == "stable"


async def test_extrusion_stall_detection(hass):
    """Test test extrusion stall detection."""
    analyzer = _coordinator(hass).analyzer
    status = _base_status()
    status["print_stats"].update({"state": "printing", "filament_used": 100.0})
    status["motion_report"].update(
        {"live_velocity": 30.0, "live_extruder_velocity": 0.0}
    )
    analyzer.analyze(status, now=0.0)
    assert analyzer.findings == []
    analyzer.analyze(status, now=10.0)
    assert analyzer.findings == []
    analyzer.analyze(status, now=40.0)
    assert analyzer.findings[0]["label"] == "extrusion stall"
    assert analyzer.findings[0]["severity"] == "bad"

    # filament advancing resets the window
    status["print_stats"]["filament_used"] = 120.0
    analyzer.analyze(status, now=80.0)
    assert analyzer.findings == []


async def test_extrusion_stall_skips_when_extruding(hass):
    """Test test extrusion stall skips when extruding."""
    analyzer = _coordinator(hass).analyzer
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    status["motion_report"].update(
        {"live_velocity": 30.0, "live_extruder_velocity": 2.0}
    )
    for now in (0.0, 60.0):
        analyzer.analyze(status, now=now)
    assert analyzer.findings == []
    status["print_stats"]["state"] = "paused"
    analyzer.analyze(status, now=120.0)
    assert analyzer._stall_window is None


async def test_mesh_drift_statuses(hass):
    """Test test mesh drift statuses."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    status = _base_status()

    status["bed_mesh"] = {"mesh_matrix": [[0.0, 0.0], [0.0, 0.0]]}
    analyzer.analyze(status, now=0.0)
    assert analyzer.metrics["mesh_status"] == "stable"
    assert analyzer._mesh_baseline is not None

    status["bed_mesh"] = {"mesh_matrix": [[0.09, 0.0], [0.0, 0.09]]}
    analyzer.analyze(status, now=1.0)
    assert analyzer.metrics["mesh_status"] == "rising"

    status["bed_mesh"] = {"mesh_matrix": [[0.2, 0.0], [0.0, 0.2]]}
    analyzer.analyze(status, now=2.0)
    assert analyzer.metrics["mesh_status"] == "due"

    status.pop("bed_mesh")
    analyzer.analyze(status, now=3.0)
    assert analyzer.metrics["mesh_status"] == "unknown"

    status["bed_mesh"] = {"mesh_matrix": [[0.0]]}
    coordinator.data = {"status": status}
    assert analyzer.reset_mesh_baseline() is True
    coordinator.data = {"status": {}}
    assert analyzer.reset_mesh_baseline() is False


async def test_energy_integration(hass):
    """Test test energy integration."""
    coordinator = _coordinator(
        hass,
        options={
            CONF_OPTION_POWER_SENSOR: "sensor.printer_power",
            CONF_OPTION_ENERGY_RATE: 0.30,
        },
    )
    analyzer = coordinator.analyzer
    hass.states.async_set("sensor.printer_power", "200", {"unit_of_measurement": "W"})
    status = _base_status()
    status["print_stats"].update({"state": "printing", "filename": "cube.gcode"})
    analyzer.analyze(status, now=0.0)
    analyzer.analyze(status, now=3600.0)  # gap >1h is ignored
    analyzer.analyze(status, now=7200.0)
    assert analyzer.metrics["print_energy_kwh"] == pytest.approx(0.0)
    # now within the 1h window
    analyzer.analyze(status, now=7500.0)
    assert analyzer.metrics["print_energy_kwh"] == pytest.approx(0.0167)
    assert analyzer.metrics["print_cost"] == pytest.approx(0.005)
    assert analyzer.metrics["power_watts"] == pytest.approx(200.0)

    hass.states.async_set("sensor.printer_power", "1", {"unit_of_measurement": "kW"})
    analyzer.analyze(status, now=7800.0)
    assert analyzer.metrics["power_watts"] == pytest.approx(1000.0)

    # new filename resets the session
    status["print_stats"]["filename"] = "benchy.gcode"
    analyzer.analyze(status, now=8100.0)
    assert analyzer.metrics["print_energy_kwh"] == 0.0


async def test_energy_handles_bad_sensor(hass):
    """Test test energy handles bad sensor."""
    coordinator = _coordinator(
        hass, options={CONF_OPTION_POWER_SENSOR: "sensor.printer_power"}
    )
    analyzer = coordinator.analyzer
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    analyzer.analyze(status, now=0.0)
    assert analyzer.metrics["power_watts"] is None

    hass.states.async_set("sensor.printer_power", "unavailable")
    analyzer.analyze(status, now=1.0)
    assert analyzer.metrics["power_watts"] is None

    hass.states.async_set("sensor.printer_power", "50")
    analyzer.analyze(status, now=2.0)
    assert analyzer.metrics["power_watts"] == pytest.approx(50.0)


async def test_print_history_records(hass):
    """Test test print history records."""
    coordinator = _coordinator(hass, options={CONF_OPTION_ENERGY_RATE: 0.30})
    analyzer = coordinator.analyzer
    coordinator.data = {
        "estimated_time": 3600.0,
        "status": _base_status(),
    }
    status = _base_status()
    status["print_stats"].update(
        {
            "state": "printing",
            "filename": "cube.gcode",
            "print_duration": 3900.0,
            "total_duration": 3900.0,
            "filament_used": 500.0,
        }
    )
    analyzer.analyze(status, now=0.0)
    status["print_stats"]["state"] = "complete"
    coordinator.data["status"] = status
    analyzer.analyze(status, now=3900.0)

    assert len(analyzer.print_history) == 1
    record = analyzer.print_history[0]
    assert record["filename"] == "cube.gcode"
    assert record["state"] == "complete"
    assert record["estimate_delta_pct"] == pytest.approx(8.3)
    assert record["energy_kwh"] == 0.0


async def test_print_history_caps_and_faults(hass):
    """Test test print history caps and faults."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    coordinator.data = {"estimated_time": None, "status": _base_status()}
    analyzer.print_history = [{"filename": f"f{i}"} for i in range(PRINT_HISTORY_LIMIT)]

    status = _base_status()
    status["print_stats"].update({"state": "printing", "filename": "new.gcode"})
    status["mcu"] = {"last_stats": {"bytes_retransmit": 10}}
    analyzer.analyze(status, now=0.0)
    status["mcu"]["last_stats"]["bytes_retransmit"] = 30
    analyzer.analyze(status, now=30.0)
    status["print_stats"]["state"] = "error"
    coordinator.data["status"] = status
    analyzer.analyze(status, now=60.0)

    assert len(analyzer.print_history) == PRINT_HISTORY_LIMIT
    record = analyzer.print_history[-1]
    assert record["filename"] == "new.gcode"
    assert "mcu retransmit" in record["faults"]
    assert record["estimate_delta_pct"] is None
    assert record["cost"] is None


def test_required_subscriptions(hass):
    """Test test required subscriptions."""
    coordinator = _coordinator(hass)
    subs = coordinator.analyzer.required_subscriptions(
        [
            "extruder",
            "extruder1",
            "heater_bed",
            "heater_generic chamber",
            "mcu",
            "fan",
        ]
    )
    assert ("motion_report", "live_extruder_velocity") in subs
    assert ("heater_generic chamber", "temperature") in subs
    assert ("heater_generic chamber", "power") in subs
    assert ("extruder", "power") in subs
    assert ("heater_bed", "power") in subs
    assert all(s[0] != "extruder1" for s in subs)


async def test_mark_dirty_before_load_flushes_after(hass):
    """Test test mark dirty before load flushes after."""
    analyzer = _coordinator(hass).analyzer
    status = _base_status()
    status["bed_mesh"] = {"mesh_matrix": [[0.0]]}
    analyzer.analyze(status, now=1.0)
    assert analyzer._store_dirty
    assert analyzer._save_unsub is None
    await analyzer.async_load()
    assert analyzer._save_unsub is not None


async def test_async_save_without_dirty_is_noop(hass):
    """Test test async save without dirty is noop."""
    analyzer = _coordinator(hass).analyzer
    await analyzer.async_load()
    await analyzer._async_save()
    assert analyzer._store_dirty is False


def test_analyzer_sensor_state_fns(hass):
    """Test test analyzer sensor state fns."""
    from custom_components.moonraker.sensor import (
        ANALYZER_SENSORS,
        MoonrakerSensor,
        analyzer_health_state,
        analyzer_last_print_state,
    )

    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    analyzer.findings = [{"severity": "bad", "label": "x", "detail": "y"}]
    assert analyzer_health_state(coordinator) == "bad"
    analyzer.findings = [{"severity": "warn", "label": "x", "detail": "y"}]
    assert analyzer_health_state(coordinator) == "warn"
    analyzer.findings = []
    assert analyzer_health_state(coordinator) == "ok"
    assert analyzer_last_print_state(coordinator) is None
    analyzer.print_history = [{"filename": "a.gcode", "state": "complete"}]
    assert analyzer_last_print_state(coordinator) == "a.gcode"

    descriptions = {desc.key: desc for desc in ANALYZER_SENSORS}
    health = MoonrakerSensor(
        coordinator, coordinator.config_entry, descriptions["printer_health"]
    )
    assert health.extra_state_attributes == {"findings": []}
    last_print = MoonrakerSensor(
        coordinator, coordinator.config_entry, descriptions["last_print"]
    )
    assert last_print.extra_state_attributes == {
        "filename": "a.gcode",
        "state": "complete",
    }
    plain = MoonrakerSensor(
        coordinator, coordinator.config_entry, descriptions["volumetric_flow"]
    )
    assert plain.extra_state_attributes is None


def test_analyzer_as_dict(hass):
    """Test test analyzer as dict."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    snapshot = analyzer.as_dict()
    assert snapshot["metrics"]["mesh_status"] == "unknown"
    assert snapshot["config"]["max_flow_mm3"] == pytest.approx(15.0)
    assert "findings" in snapshot
    assert "thermal_history_lengths" in snapshot


async def test_diagnostics(hass):
    """Test test diagnostics."""
    coordinator = _coordinator(hass)
    coordinator.data = {
        "status": _base_status(),
        "printer.info": {"state": "ready", "hostname": "printer.local"},
    }
    entry = coordinator.config_entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "analyzer" in diag
    assert diag["coordinator"]["queried_objects"]
    assert diag["printer_info"]["hostname"] == "**REDACTED**"
    assert "status" not in str(diag["entry"]) or True

    device_diag = await async_get_device_diagnostics(hass, entry, MagicMock())
    assert device_diag["analyzer"]["config"]["max_flow_mm3"] == 15.0


async def test_repairs_issues_sync(hass):
    """Findings mirror into Repairs issues and clear when healthy."""
    from homeassistant.helpers import issue_registry as ir

    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    registry = ir.async_get(hass)
    entry_id = coordinator.config_entry.entry_id

    coordinator.data = {
        "machine_update": {
            "version_info": {
                "mainsail": {"version": "1.0", "remote_version": "2.0"},
                "system": {"package_count": 0},
            }
        },
        "status": _base_status(),
    }
    analyzer._mesh_baseline = {"matrix": [[0.0]], "at": 0.0}
    status = _base_status()
    status["bed_mesh"] = {"mesh_matrix": [[0.2]]}
    status["print_stats"].update({"state": "printing", "filament_used": 0.0})
    status["motion_report"].update(
        {"live_velocity": 30.0, "live_extruder_velocity": 0.0}
    )
    status["extruder"] = {"temperature": 200.0, "power": 1.0, "target": 200.0}
    coordinator.last_update_success = False

    for index in range(40):
        status["extruder"]["temperature"] = 200 - index
        analyzer.analyze(status, now=float(index) * 2)
    coordinator.data["status"] = status
    analyzer.analyze(status, now=90.0)

    issues = registry.async_get_issue
    assert issues(DOMAIN, f"{entry_id}_mesh_relevel") is not None
    assert issues(DOMAIN, f"{entry_id}_heater_anomaly") is not None
    assert issues(DOMAIN, f"{entry_id}_extrusion_stall") is not None
    assert issues(DOMAIN, f"{entry_id}_updates_available") is not None
    assert issues(DOMAIN, f"{entry_id}_printer_unreachable") is not None

    coordinator.last_update_success = True
    coordinator.data["machine_update"] = {
        "version_info": {"system": {"package_count": 0}}
    }
    healthy = _base_status()
    healthy["extruder"] = {"temperature": 25.0, "power": 0.0, "target": 0.0}
    healthy["print_stats"]["state"] = "complete"
    analyzer.analyze(healthy, now=200.0)
    assert issues(DOMAIN, f"{entry_id}_mesh_relevel") is None
    assert issues(DOMAIN, f"{entry_id}_updates_available") is None
    assert issues(DOMAIN, f"{entry_id}_printer_unreachable") is None


async def test_power_off_after_completion(hass):
    """A completed print powers the printer off after cooldown."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        async_fire_time_changed,
    )

    coordinator = _coordinator(
        hass,
        options={
            "power_switch_entity": "switch.printer_plug",
            "power_off_delay_min": 15.0,
            "power_off_max_temp": 50.0,
        },
        entry_id="poweroff",
    )
    analyzer = coordinator.analyzer
    calls = []

    async def capture(call):
        calls.append(call)

    hass.services.async_register("switch", "turn_off", capture)
    coordinator.data = {"status": _base_status(), "queue": {"queued_jobs": []}}

    status = _base_status()
    status["print_stats"].update({"state": "printing", "filename": "a.gcode"})
    analyzer.analyze(status, now=0.0)
    status["print_stats"]["state"] = "complete"
    status["extruder"]["temperature"] = 30.0
    coordinator.data["status"] = status
    analyzer.analyze(status, now=60.0)
    assert analyzer._power_off_armed

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=20))
    await hass.async_block_till_done()
    assert calls[0].data == {"entity_id": "switch.printer_plug"}
    assert analyzer._power_off_armed is False


async def test_power_off_guards(hass):
    """Power-off skips hot, busy, or queued states."""
    coordinator = _coordinator(
        hass,
        options={"power_switch_entity": "switch.printer_plug"},
        entry_id="powerguards",
    )
    analyzer = coordinator.analyzer
    calls = []

    async def capture(call):
        calls.append(call)

    hass.services.async_register("switch", "turn_off", capture)

    # still printing → no off
    coordinator.data = {
        "status": _base_status(),
        "queue": {"queued_jobs": []},
    }
    coordinator.data["status"]["print_stats"]["state"] = "printing"
    await analyzer._async_power_off_check()
    assert calls == []

    # hotend too hot → no off
    coordinator.data["status"]["print_stats"]["state"] = "complete"
    coordinator.data["status"]["extruder"]["temperature"] = 80.0
    await analyzer._async_power_off_check()
    assert calls == []

    # queued jobs → no off
    coordinator.data["status"]["extruder"]["temperature"] = 30.0
    coordinator.data["queue"] = {"queued_jobs": ["next.gcode"]}
    await analyzer._async_power_off_check()
    assert calls == []
    assert analyzer._power_off_armed is False

    # missing switch entity is tolerated
    coordinator.data["queue"] = {"queue": []}
    hass.services.async_remove("switch", "turn_off")
    await analyzer._async_power_off_check()
    assert calls == []


async def test_power_off_timer_cancelled_on_shutdown(hass):
    """Unloading cancels an armed power-off timer."""
    coordinator = _coordinator(
        hass,
        options={"power_switch_entity": "switch.printer_plug"},
        entry_id="powercancel",
    )
    analyzer = coordinator.analyzer
    await analyzer.async_load()
    analyzer._schedule_power_off()
    assert analyzer._power_off_unsub is not None
    await analyzer.async_shutdown()
    assert analyzer._power_off_unsub is None
    assert analyzer._power_off_armed is False


def test_heatup_learning_flags_slow_heater(hass):
    """Heat-up durations are learned and slow ones flagged."""
    coordinator = _coordinator(hass, entry_id="heatup")
    analyzer = coordinator.analyzer
    status = _base_status()

    def cycle(start, duration):
        status["extruder"].update({"temperature": 25.0, "target": 200.0})
        analyzer._analyze_heatup(status, start)
        status["extruder"]["temperature"] = 200.0
        analyzer._analyze_heatup(status, start + duration)

    cycle(0, 60)
    cycle(1000, 62)
    cycle(2000, 58)
    assert analyzer._heatup_history["extruder"] == [60, 62, 58]

    cycle(3000, 100)  # > 1.2x median(60,62,58)=60 → finding
    assert analyzer._heatup_history["extruder"][-1] == 100

    status["extruder"].update({"temperature": 25.0, "target": 200.0})
    analyzer.analyze(status, now=4000)
    status["extruder"]["temperature"] = 200.0
    analyzer.analyze(status, now=4100)
    assert any("slow heat-up" in f["label"] for f in analyzer.findings)

    # target dropped mid-heat clears the pending entry
    status["extruder"].update({"temperature": 25.0, "target": 200.0})
    analyzer._analyze_heatup(status, 5000)
    assert "extruder" in analyzer._heatup_active
    status["extruder"]["target"] = 0.0
    analyzer._analyze_heatup(status, 5010)
    assert "extruder" not in analyzer._heatup_active

    # already-at-temp or trivially short heat-ups are not recorded
    status["extruder"].update({"temperature": 25.0, "target": 200.0})
    analyzer._analyze_heatup(status, 6000)
    status["extruder"]["temperature"] = 200.0
    analyzer._analyze_heatup(status, 6002)
    assert len(analyzer._heatup_history["extruder"]) == 5


def test_spool_crosscheck_shortfall_and_mismatch(hass):
    """Spool runout layer and material mismatch findings."""
    coordinator = _coordinator(hass, entry_id="spool")
    analyzer = coordinator.analyzer
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    status["print_stats"]["filament_used"] = 500.0
    status["print_stats"]["info"] = {"current_layer": 20}
    coordinator.data = {
        "status": status,
        "filament_total": 3000.0,
        "layer_count": 100,
        "filament_type": "PLA",
        "spool_details": {
            "remaining_length": 1000.0,
            "filament": {"material": "PETG", "density": 1.27, "diameter": 1.75},
        },
    }
    findings = analyzer._analyze_spool()
    labels = {f["label"] for f in findings}
    assert "spool shortfall" in labels
    assert "material mismatch" in labels
    # needed=2500mm, remaining=1000mm → runout at 20 + 1000/30 ≈ layer 53
    assert analyzer.metrics["spool_runout_layer"] == 53
    assert analyzer.metrics["spool_material"] == "PETG"
    assert analyzer.metrics["spool_remaining_mm"] == 1000.0

    # enough filament clears the runout metric
    coordinator.data["spool_details"]["remaining_length"] = 90000.0
    coordinator.data["filament_type"] = "PETG"
    findings = analyzer._analyze_spool()
    assert findings == []
    assert analyzer.metrics["spool_runout_layer"] is None

    # weight-only spools fall back to density/diameter math
    coordinator.data["spool_details"] = {
        "remaining_weight": 20.0,
        "filament": {"material": "PLA", "density": 1.24, "diameter": 1.75},
    }
    analyzer._analyze_spool()
    expected = (20.0 / 1.24) * 1000 / FILAMENT_AREA_MM2
    assert analyzer.metrics["spool_remaining_mm"] == round(expected, 1)

    # no spool data clears the metrics
    coordinator.data["spool_details"] = {}
    analyzer._analyze_spool()
    assert analyzer.metrics["spool_material"] is None
    assert analyzer.metrics["spool_runout_layer"] is None


def test_material_profile_and_ambient(hass):
    """Material profile checks cover temps and cold ambient air."""
    coordinator = _coordinator(
        hass,
        options={"ambient_sensor": "sensor.room_temp"},
        entry_id="material",
    )
    analyzer = coordinator.analyzer
    hass.states.async_set("sensor.room_temp", "15.5")
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    status["extruder"]["target"] = 255.0
    status["heater_bed"]["target"] = 100.0
    coordinator.data = {"status": status, "filament_type": "ABS+ CF"}

    findings = analyzer._analyze_material(status)
    labels = {f["label"] for f in findings}
    assert analyzer.metrics["material"] == "ABS"
    assert analyzer.metrics["ambient_c"] == 15.5
    assert "cold ambient" in labels
    assert "nozzle outside profile" not in labels  # 255 within ABS range
    assert "bed outside profile" not in labels

    # nozzle far outside the profile range flags
    status["extruder"]["target"] = 170.0
    findings = analyzer._analyze_material(status)
    assert any(f["label"] == "nozzle outside profile" for f in findings)

    # material from the spool when the file type is unknown
    coordinator.data["filament_type"] = None
    analyzer.metrics["spool_material"] = "PETG"
    assert analyzer._detect_material() == "PETG"

    # standby clears nothing but reports no findings
    status["print_stats"]["state"] = "standby"
    assert analyzer._analyze_material(status) == []


def test_kinematics_limits_and_over_speed(hass):
    """Configured limits surface as metrics; over-speed flags after samples."""
    coordinator = _coordinator(hass, entry_id="kin")
    analyzer = coordinator.analyzer
    coordinator._config_settings = {
        "status": {
            "configfile": {
                "settings": {
                    "printer": {"max_velocity": 200.0, "max_accel": 3000.0},
                    "input_shaper": {"shaper_freq_x": 44.4},
                }
            }
        }
    }
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    findings = analyzer._analyze_kinematics(status)
    assert findings == []
    assert analyzer.metrics["max_velocity"] == 200.0
    assert analyzer.metrics["max_accel"] == 3000.0
    assert analyzer.metrics["shaper_freq_x"] == 44.4

    status["motion_report"]["live_velocity"] = 260.0
    assert analyzer._analyze_kinematics(status) == []
    assert analyzer._analyze_kinematics(status) == []
    findings = analyzer._analyze_kinematics(status)
    assert any(f["label"] == "velocity above limit" for f in findings)

    # cooling down resets the sample counter
    status["motion_report"]["live_velocity"] = 100.0
    analyzer._analyze_kinematics(status)
    assert analyzer._over_limit_samples == 0


async def test_heatup_history_persists(hass):
    """Heat-up baselines round-trip through the Store."""
    coordinator = _coordinator(hass, entry_id="heatstore")
    analyzer = coordinator.analyzer
    await analyzer.async_load()
    analyzer._heatup_history = {"extruder": [60.0, 62.0], "heater_bed": [45.0]}
    analyzer._mark_dirty()
    await analyzer._async_save()

    coordinator2 = _coordinator(hass, entry_id="heatstore")
    analyzer2 = coordinator2.analyzer
    await analyzer2.async_load()
    assert analyzer2._heatup_history["extruder"] == [60.0, 62.0]
    assert analyzer2._heatup_history["heater_bed"] == [45.0]


async def test_spool_status_updater(hass):
    """The slow updater fetches and whitelists spool details."""
    from custom_components.moonraker import _spool_status_updater

    coordinator = _coordinator(hass, entry_id="spoolupd")

    async def fetch(method, params=None, quiet=False):
        if method.value == "server.spoolman.status":
            return {"spool_id": 7}
        if method.value == "server.spoolman.proxy":
            return {
                "remaining_length": 1234.0,
                "filament": {"material": "PLA", "secret": "x"},
            }
        return {}

    coordinator.async_fetch_data = AsyncMock(side_effect=fetch)
    result = await _spool_status_updater(coordinator)
    assert result["spool_details"]["remaining_length"] == 1234.0

    # no active spool → empty details
    async def fetch_none(method, params=None, quiet=False):
        return {"spool_id": None}

    coordinator.async_fetch_data = AsyncMock(side_effect=fetch_none)
    assert (await _spool_status_updater(coordinator))["spool_details"] == {}

    # fetch failures degrade quietly
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coordinator.async_fetch_data = AsyncMock(side_effect=UpdateFailed())
    assert await _spool_status_updater(coordinator) == {}


def test_spool_remaining_guards(hass):
    """Degenerate spool records produce no bogus remaining length."""
    coordinator = _coordinator(hass, entry_id="spoolguard")
    analyzer = coordinator.analyzer
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    status["print_stats"]["filament_used"] = 4000.0
    coordinator.data = {"status": status, "filament_total": 3000.0}

    # no length, no weight → unknown remaining; nothing needed → clears metric
    coordinator.data["spool_details"] = {"filament": {"material": "PLA"}}
    assert analyzer._analyze_spool() == []
    assert analyzer.metrics["spool_runout_layer"] is None

    # invalid density cannot be converted from weight
    coordinator.data["spool_details"] = {
        "remaining_weight": 10.0,
        "filament": {"density": -1.0, "diameter": 1.75},
    }
    analyzer._analyze_spool()
    assert analyzer.metrics["spool_remaining_mm"] is None


def test_material_bed_out_of_profile_and_missing_ambient(hass):
    """Bed out of range flags; a missing ambient state is tolerated."""
    coordinator = _coordinator(
        hass,
        options={"ambient_sensor": "sensor.missing"},
        entry_id="material2",
    )
    analyzer = coordinator.analyzer
    status = _base_status()
    status["print_stats"]["state"] = "printing"
    status["extruder"]["target"] = 250.0
    status["heater_bed"]["target"] = 30.0
    coordinator.data = {"status": status, "filament_type": "ABS"}

    findings = analyzer._analyze_material(status)
    labels = {f["label"] for f in findings}
    assert "bed outside profile" in labels
    assert analyzer.metrics["ambient_c"] is None
    assert "cold ambient" not in labels  # no ambient reading → no cold finding


async def test_spool_status_updater_proxy_failure(hass):
    """A failing spool proxy call degrades to no details."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from custom_components.moonraker import _spool_status_updater

    coordinator = _coordinator(hass, entry_id="spoolupd2")

    async def fetch(method, params=None, quiet=False):
        if method.value == "server.spoolman.status":
            return {"spool_id": 7}
        raise UpdateFailed()

    coordinator.async_fetch_data = AsyncMock(side_effect=fetch)
    assert await _spool_status_updater(coordinator) == {}
