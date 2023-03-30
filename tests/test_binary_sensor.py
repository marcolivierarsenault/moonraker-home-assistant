""" Binary_sensor Tests"""
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_runout_filament_sensor_missing(
    hass, get_data, get_printer_info, get_printer_objects_list
):
    get_data["status"].pop("filament_switch_sensor filament_sensor_1", None)
    get_data["status"].pop("filament_switch_sensor filament_sensor_2", None)
    get_printer_objects_list["objects"].remove(
        "filament_switch_sensor filament_sensor_1"
    )
    get_printer_objects_list["objects"].remove(
        "filament_switch_sensor filament_sensor_2"
    )

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **get_printer_objects_list},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state is None
    state = hass.states.get("binary_sensor.mainsail_filament_sensor_2")
    assert state is None


async def test_runout_filament_sensor(
    hass, get_data, get_printer_info, get_printer_objects_list
):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **get_printer_objects_list},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state.state == "on"


async def test_multiple_runout_filament_sensor(
    hass, get_data, get_printer_info, get_printer_objects_list
):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **get_printer_objects_list},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state.state == "on"

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_2")
    assert state.state == "on"


async def test_runout_filament_sensor_off(
    hass, get_data, get_printer_info, get_printer_objects_list
):
    get_data["status"]["filament_switch_sensor filament_sensor_1"][
        "filament_detected"
    ] = False

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **get_printer_objects_list},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state.state == "off"
