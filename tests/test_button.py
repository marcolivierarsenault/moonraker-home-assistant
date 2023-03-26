""" Button Tests"""
from unittest.mock import patch

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_emergency_button(hass, get_data, get_printer_info, get_gcode_help):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, "result": "ok", **get_gcode_help},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: "button.mainsail_emergency_stop",
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(METHODS.PRINTER_EMERGENCY_STOP.value)


async def test_gcode_macro(hass, get_data, get_printer_info, get_gcode_help):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, "result": "ok", **get_gcode_help},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: "button.mainsail_macro_start_print",
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="START_PRINT"
        )
