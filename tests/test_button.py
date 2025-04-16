"""Button Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


@pytest.mark.parametrize(
    "button, method",
    [
        ("mainsail_emergency_stop", METHODS.PRINTER_EMERGENCY_STOP.value),
        ("mainsail_firmware_restart", METHODS.PRINTER_FIRMWARE_RESTART.value),
        ("mainsail_host_restart", METHODS.HOST_RESTART.value),
        ("mainsail_host_shutdown", METHODS.HOST_SHUTDOWN.value),
        ("mainsail_pause_print", METHODS.PRINTER_PRINT_PAUSE.value),
        ("mainsail_resume_print", METHODS.PRINTER_PRINT_RESUME.value),
        ("mainsail_server_restart", METHODS.SERVER_RESTART.value),
        ("mainsail_cancel_print", METHODS.PRINTER_PRINT_CANCEL.value),
        ("mainsail_start_print_from_queue", METHODS.SERVER_JOB_QUEUE_START.value),
    ],
)
async def test_buttons(hass, button, method):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: f"button.{button}",
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(method)


async def test_gcode_macro(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
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


async def test_disabled_buttons(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("button.mainsail_macro_end_print")
    assert entity
    assert not entity.disabled

    entity = entity_registry.async_get("button.mainsail_macro_set_pause_next_layer")
    assert entity
    assert entity.disabled
