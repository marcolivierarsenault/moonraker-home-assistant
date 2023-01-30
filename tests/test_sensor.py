"""Test moonraker sensor."""
from unittest.mock import patch
import datetime as dt

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


async def test_sensor_services(hass, get_data, bypass_connect_client):
    """Test sensor services."""
    # Create a mock entry so we don't have to go through config flow
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.get_data", return_value=get_data
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.bed_target")

    assert state.state == "0.0"

    with patch(
        "custom_components.moonraker.MoonrakerApiClient.get_data", return_value=get_data
    ), patch(
        "custom_components.moonraker.MoonrakerDataUpdateCoordinator._async_update_data"
    ):
        async_fire_time_changed(
            hass,
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1),
        )
        await hass.async_block_till_done()

    assert state.state == "0.0"
