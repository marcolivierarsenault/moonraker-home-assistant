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
from custom_components.moonraker.sensor import calculate_pct_job

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


@pytest.fixture(name="data_for_calculate_pct")
def data_for_calculate_pct_fixture():
    """data_for_calculate_pct"""
    return {
        "estimated_time": 10,
        "status": {
            "print_stats": {"print_duration": 6, "filament_used": 1},
            "display_status": {"progress": 0.60},
        },
        "filament_total": 2,
    }


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
        ("mainsail_current_display_message", "Custom Message"),
        ("mainsail_printer_message", "Printer is ready"),
        ("mainsail_current_print_state", "printing"),
        ("mainsail_current_print_message", ""),
        ("mainsail_print_projected_total_duration", "9197.46"),
        ("mainsail_print_time_left", "1182.94"),
        ("mainsail_print_duration", "133.58"),
        ("mainsail_filament_used", "5.0"),
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


async def test_eta(hass, get_data, get_printer_info):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_eta")

    assert dt.datetime.strptime(state.state, "%Y-%m-%dT%H:%M:%S%z") < dt.datetime.now(
        dt.timezone.utc
    ) + dt.timedelta(0, 1182.94 + 2)
    assert dt.datetime.strptime(state.state, "%Y-%m-%dT%H:%M:%S%z") > dt.datetime.now(
        dt.timezone.utc
    ) + dt.timedelta(0, 1182.94 - 2)


async def test_eta_no_current_data(hass, get_data, get_printer_info):
    get_data["status"]["print_stats"]["print_duration"] = 0
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_eta")

    assert state.state == "unknown"


async def test_calculate_pct_job(data_for_calculate_pct):
    assert calculate_pct_job(data_for_calculate_pct) == 0.55


async def test_calculate_pct_job_no_time(data_for_calculate_pct):
    data_for_calculate_pct["estimated_time"] = 0
    assert calculate_pct_job(data_for_calculate_pct) == 0


async def test_calculate_pct_job_no_filament(data_for_calculate_pct):
    data_for_calculate_pct["filament_total"] = 0
    assert calculate_pct_job(data_for_calculate_pct) == 0
