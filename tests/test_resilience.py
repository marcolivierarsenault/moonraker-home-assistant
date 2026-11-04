"""Resilience and load tests for the analyzer and coordinator paths."""

from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advance_moonraker_control import MoonrakerDataUpdateCoordinator

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.start"),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
        patch(
            "custom_components.advance_moonraker_control._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


def _coordinator(hass, entry_id="resilience"):
    config_entry = MockConfigEntry(
        domain="advance_moonraker_control", data=MOCK_CONFIG, entry_id=entry_id
    )
    return MoonrakerDataUpdateCoordinator(
        hass,
        client=MagicMock(),
        config_entry=config_entry,
        api_device_name="printer",
    )


@pytest.mark.parametrize(
    "status",
    [
        None,
        {},
        {"print_stats": None},
        {"print_stats": "not-a-dict"},
        {"print_stats": {"state": 42}},
        {"extruder": "hot", "heater_bed": [1, 2]},
        {"motion_report": {"live_velocity": "fast"}},
        {"bed_mesh": {"mesh_matrix": "broken"}},
        {"toolhead": {"position": "nowhere"}},
        {"print_stats": {"state": "printing", "info": []}},
        {"system_stats": {"cputemp": float("nan")}},
    ],
)
def test_analyze_tolerates_malformed_status(hass, status):
    """Garbage payloads never crash the analyzer."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    analyzer.analyze(status)
    assert isinstance(analyzer.findings, list)


def test_analyze_state_stays_bounded(hass):
    """A long stream of updates keeps histories inside their limits."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    status = {
        "print_stats": {
            "state": "printing",
            "filename": "long.gcode",
            "filament_used": 100.0,
            "info": {"current_layer": 5},
        },
        "extruder": {"temperature": 200.0, "power": 0.5, "target": 200.0},
        "heater_bed": {"temperature": 60.0, "power": 0.4, "target": 60.0},
        "motion_report": {"live_velocity": 40.0, "live_extruder_velocity": 4.0},
        "bed_mesh": {"mesh_matrix": [[0.0, 0.0], [0.0, 0.0]]},
    }
    for index in range(2000):
        status["extruder"]["temperature"] = 200.0 + (index % 5)
        analyzer.analyze(status, now=float(index))

    for history in analyzer.thermal_history.values():
        assert isinstance(history, deque)
        assert len(history) <= 120
    assert len(analyzer.checkpoints) <= analyzer.checkpoints.maxlen
    assert len(analyzer.print_history) <= 20


async def test_load_shutdown_cycle_is_clean(hass):
    """Repeated load/save/shutdown leaves no pending timers."""
    coordinator = _coordinator(hass)
    analyzer = coordinator.analyzer
    for _ in range(3):
        await analyzer.async_load()
        analyzer.analyze(
            {
                "print_stats": {"state": "printing", "filename": "x.gcode"},
                "extruder": {"temperature": 200, "power": 0.5, "target": 200},
            },
            now=1.0,
        )
        await analyzer.async_shutdown()
        assert analyzer._save_unsub is None
        assert analyzer._power_off_unsub is None
        assert analyzer._vision_task is None


def test_fleet_analyzers_are_independent(hass):
    """Ten coordinators keep separate metrics, baselines, and findings."""
    analyzers = [_coordinator(hass, entry_id=f"fleet{i}").analyzer for i in range(10)]
    status = {
        "print_stats": {
            "state": "printing",
            "filename": "f.gcode",
            "filament_used": 10.0,
        },
        "extruder": {"temperature": 200.0, "power": 0.5, "target": 200.0},
        "bed_mesh": {"mesh_matrix": [[0.0]]},
    }
    for analyzer in analyzers:
        analyzer.analyze(dict(status), now=0.0)
    assert len({id(item._mesh_baseline) for item in analyzers}) == 10
    assert all(item.metrics.get("mesh_status") == "stable" for item in analyzers)


async def test_updater_failure_degrades_quietly(hass):
    """A failing data updater surfaces as UpdateFailed, not a crash."""
    coordinator = _coordinator(hass)
    coordinator.data = {"status": {}}

    async def broken(_coordinator):
        raise RuntimeError("moonraker unreachable")

    coordinator.updaters = [broken]
    coordinator._updater_every = {broken: 1}
    coordinator._update_cycle = 0

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
