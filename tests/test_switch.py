"""Switch Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.const import ATTR_ENTITY_ID
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
