"""Button Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button.const import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG


async def _enable_button_entity(hass, config_entry, entity_id: str):
    """Enable a button entity if it is disabled by default."""
    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get(entity_id)
    assert entity
    if entity.disabled:
        entity_registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()
        entity = entity_registry.async_get(entity_id)
        assert entity
        assert not entity.disabled
    state = hass.states.get(entity_id)
    assert state is not None
    return entity


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
    entity_id = f"button.{button}"
    await _enable_button_entity(hass, config_entry, entity_id)

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: entity_id,
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
    entity_id = "button.mainsail_macro_start_print"
    await _enable_button_entity(hass, config_entry, entity_id)

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: entity_id,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="START_PRINT"
        )


async def test_gcode_macro_attributes(hass):
    """Test macro attributes are exposed."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = "button.mainsail_macro_start_print"
    await _enable_button_entity(hass, config_entry, entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["filament_used"] == 0
    assert state.attributes["last_service_date"] == "2023-10-01"


async def test_services(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = "button.mainsail_stop_klipper"
    await _enable_button_entity(hass, config_entry, entity_id)

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: entity_id,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.MACHINE_SERVICES_STOP.value, service="klipper"
        )


async def test_disabled_buttons(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    enabled_buttons = [
        "button.mainsail_emergency_stop",
        "button.mainsail_pause_print",
        "button.mainsail_resume_print",
        "button.mainsail_cancel_print",
        "button.mainsail_home_x_axis",
        "button.mainsail_home_y_axis",
        "button.mainsail_home_z_axis",
        "button.mainsail_home_all_axes",
    ]
    for entity_id in enabled_buttons:
        entity = entity_registry.async_get(entity_id)
        assert entity
        assert not entity.disabled

    disabled_buttons = [
        "button.mainsail_server_restart",
        "button.mainsail_host_restart",
        "button.mainsail_host_shutdown",
        "button.mainsail_firmware_restart",
        "button.mainsail_start_print_from_queue",
        "button.mainsail_macro_start_print",
        "button.mainsail_macro_end_print",
        "button.mainsail_macro_set_pause_next_layer",
        "button.mainsail_stop_klipper",
    ]

    for entity_id in disabled_buttons:
        entity = entity_registry.async_get(entity_id)
        assert entity
        assert entity.disabled


@pytest.mark.parametrize(
    "button, gcode",
    [
        ("mainsail_home_x_axis", "G28 X"),
        ("mainsail_home_y_axis", "G28 Y"),
        ("mainsail_home_z_axis", "G28 Z"),
        ("mainsail_home_all_axes", "G28"),
    ],
)
async def test_home_axis_buttons(hass, button, gcode):
    """Test home axis buttons send correct G-code."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = f"button.{button}"
    await _enable_button_entity(hass, config_entry, entity_id)

    with patch("moonraker_api.MoonrakerClient.call_method") as mock_api:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {
                ATTR_ENTITY_ID: entity_id,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script=gcode
        )
