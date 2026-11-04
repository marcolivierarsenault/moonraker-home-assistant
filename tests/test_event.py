"""Test the Moonraker print lifecycle event entity."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advance_moonraker_control.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.start"),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
        patch(
            "custom_components.advance_moonraker_control._async_is_tcp_reachable",
            return_value=True,
        ),
    ):
        yield


async def _setup(hass, get_default_api_response):
    """Set up the integration and return the coordinator."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][config_entry.entry_id], config_entry


async def test_print_events_entity(hass, get_default_api_response):
    """Lifecycle dispatches surface as event entity events."""
    coordinator, _ = await _setup(hass, get_default_api_response)

    entity_id = "event.mainsail_print_events"
    assert hass.states.get(entity_id) is not None

    coordinator.analyzer._dispatch_print_event("print_started", "cube.gcode")
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "print_started"
    assert state.attributes["filename"] == "cube.gcode"

    coordinator.analyzer._dispatch_print_event("not_an_event", "cube.gcode")
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "print_started"


async def test_print_state_transitions_fire_events(hass, get_default_api_response):
    """Print state changes dispatch lifecycle events."""
    coordinator, _ = await _setup(hass, get_default_api_response)
    analyzer = coordinator.analyzer
    analyzer._prev_print_state = "standby"
    fired = []
    original = analyzer._dispatch_print_event
    analyzer._dispatch_print_event = lambda event, name: (
        fired.append(event),
        original(event, name),
    )

    def status(state, filename="cube.gcode"):
        return {
            "print_stats": {
                "state": state,
                "filename": filename,
                "print_duration": 1.0,
                "total_duration": 1.0,
                "filament_used": 1.0,
            }
        }

    analyzer.analyze(status("printing"), now=0.0)
    analyzer.analyze(status("paused"), now=1.0)
    analyzer.analyze(status("printing"), now=2.0)
    analyzer.analyze(status("complete"), now=3.0)
    assert fired == [
        "print_started",
        "print_paused",
        "print_resumed",
        "print_completed",
    ]


async def test_notify_service_called_on_events(hass, get_default_api_response):
    """Configured notify service receives milestone notifications."""
    calls = []

    async def capture(call):
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_phone", capture)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={"notify_service": "mobile_app_phone"},
        entry_id="notify",
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    calls.clear()
    coordinator.analyzer._notify("print_started", "cube.gcode")
    await hass.async_block_till_done()
    assert calls[0].data["data"]["actions"]

    calls.clear()
    coordinator.analyzer._notify("print_completed", "cube.gcode")
    await hass.async_block_till_done()
    assert "data" not in calls[0].data

    coordinator.analyzer._notify("mystery", "cube.gcode")
    await hass.async_block_till_done()
    assert calls[-1].data["title"] == "Printer event"


async def test_notify_skipped_without_service(hass, get_default_api_response):
    """No notify call is made without a configured service."""
    coordinator, _ = await _setup(hass, get_default_api_response)
    calls = []

    async def capture(call):
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_phone", capture)
    coordinator.analyzer._notify("print_started", "cube.gcode")
    await hass.async_block_till_done()
    assert calls == []

    # an unregistered service name is tolerated, not raised
    coordinator.analyzer.notify_service = "mobile_app_missing"
    coordinator.analyzer._notify("print_started", "cube.gcode")
    await hass.async_block_till_done()
    assert calls == []


async def test_printcast_forecast_event(hass, get_default_api_response):
    """Printcast dispatches surface as printcast_forecast entity events."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.advance_moonraker_control.const import SIGNAL_PRINTCAST

    coordinator, _ = await _setup(hass, get_default_api_response)
    entity_id = "event.mainsail_print_events"

    async_dispatcher_send(
        hass,
        f"{SIGNAL_PRINTCAST}_{coordinator.config_entry.entry_id}",
        {
            "filename": "cube.gcode",
            "score": 82,
            "verdict": "CLEAR",
            "recommendation": "go ahead",
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "printcast_forecast"
    assert state.attributes["filename"] == "cube.gcode"
    assert state.attributes["score"] == 82
    assert state.attributes["verdict"] == "CLEAR"
