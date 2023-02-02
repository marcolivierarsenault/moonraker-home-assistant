"""Test moonraker sensor."""
import pytest

from unittest.mock import patch
import datetime as dt

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


async def test_sensor_services(hass, get_data, get_printer_info):
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

    assert state.state == "0.0"

    with patch(
        "moonraker_api.MoonrakerClient.call_method", return_value=get_data
    ), patch(
        "custom_components.moonraker.MoonrakerDataUpdateCoordinator._async_update_data"
    ):
        async_fire_time_changed(
            hass,
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1),
        )
        await hass.async_block_till_done()

    assert state.state == "0.0"
