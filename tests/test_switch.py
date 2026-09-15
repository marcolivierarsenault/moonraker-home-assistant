"""Switch Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_UNAVAILABLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


# test switches
@pytest.mark.parametrize(
    "switch, switch_type",
    [
        ("mainsail_light", "power"),
        ("mainsail_printer", "power"),
        ("mainsail_output_pin_digital", "pin"),
    ],
)
async def test_switch_turn_on(hass, switch, switch_type, get_default_api_response):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: f"switch.{switch}",
            },
            blocking=True,
        )

        if switch_type == "power":
            mock_api.assert_any_call(
                METHODS.MACHINE_DEVICE_POWER_POST_DEVICE.value,
                device=switch.split("_")[1],
                action="on",
            )
        elif switch_type == "pin":
            mock_api.assert_any_call(
                METHODS.PRINTER_GCODE_SCRIPT.value,
                script=f"SET_PIN PIN={switch.split('_')[3]} VALUE=1",
            )


# test switches
@pytest.mark.parametrize(
    "switch, switch_type",
    [
        ("mainsail_light", "power"),
        ("mainsail_printer", "power"),
        ("mainsail_output_pin_digital", "pin"),
    ],
)
async def test_switch_turn_off(hass, switch, switch_type, get_default_api_response):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {
                ATTR_ENTITY_ID: f"switch.{switch}",
            },
            blocking=True,
        )

        if switch_type == "power":
            mock_api.assert_any_call(
                METHODS.MACHINE_DEVICE_POWER_POST_DEVICE.value,
                device=switch.split("_")[1],
                action="off",
            )
        elif switch_type == "pin":
            mock_api.assert_any_call(
                METHODS.PRINTER_GCODE_SCRIPT.value,
                script=f"SET_PIN PIN={switch.split('_')[3]} VALUE=0",
            )


async def test_power_devices_missing_key(hass, get_default_api_response):
    """Missing 'devices' key (e.g. Moonraker offline) must not crash setup."""
    response_without_devices = {**get_default_api_response}
    response_without_devices.pop("devices", None)

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value=response_without_devices,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state.value == "loaded"
    assert hass.states.get("switch.mainsail_printer") is None


async def test_power_device_missing_from_coordinator_data(hass, get_power_devices):
    """Power state going missing after setup marks the switch unavailable, not crashed."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("switch.mainsail_printer")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE

    get_power_devices["devices"] = []
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={"devices": []},
    ):
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("switch.mainsail_printer")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_output_pin_config_missing_skips_entity(hass, get_data):
    """An output pin with unknown config must be skipped, not guessed as digital."""
    get_data["status"]["configfile"]["settings"].pop("output_pin digital", None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("switch.mainsail_output_pin_digital") is None
