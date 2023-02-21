"""Test moonraker sensor."""
import datetime as dt
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_sensor_services_update(hass, get_data, get_printer_info):
    """Test sensor services."""
    # Create a mock entry so we don't have to go through config flow
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_bed_target")

    assert state.state == "60.0"

    get_data["status"]["heater_bed"]["target"] = 100.0

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        async_fire_time_changed(
            hass,
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.mainsail_bed_target").state == "100.0"


# test all sensors
@pytest.mark.parametrize(
    "sensor, value",
    [
        ("mainsail_bed_target", "60.0"),
        ("mainsail_bed_temperature", "60.01"),
        ("mainsail_extruder_target", "205.0"),
        ("mainsail_extruder_temperature", "205.02"),
        ("mainsail_progress", "90"),
        ("mainsail_printer_state", "ready"),
        ("mainsail_printer_message", "Printer is ready"),
        ("mainsail_current_print_state", "printing"),
        ("mainsail_current_print_message", ""),
        ("mainsail_print_projected_duration", "147.14"),
        ("mainsail_eta", "13.56"),
        ("mainsail_print_duration", "133.58"),
        ("mainsail_filament_used", "7.77"),
        ("mainsail_progress", "90"),
        ("mainsail_bed_power", "26"),
        ("mainsail_extruder_power", "66"),
    ],
)
async def test_sensors(hass, sensor, value, get_data, get_printer_info):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get(f"sensor.{sensor}")

    assert state.state == value
