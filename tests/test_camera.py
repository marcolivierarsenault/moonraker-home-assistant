"""test moonraker camera"""
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN
from homeassistant.helpers import entity_registry as er

from .const import MOCK_CONFIG


async def test_sensor_services(hass, get_data, bypass_connect_client):
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.get_data", return_value=get_data
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("camera.moonraker_camera")

    assert entry is not None
