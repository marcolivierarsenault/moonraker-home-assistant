"""test moonraker camera"""
import pytest
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN
from homeassistant.helpers import entity_registry as er

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_camera_services(hass, get_data, get_printer_info, get_camera_info):
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **get_camera_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("camera.mainsail_webcam")

    assert entry is not None


async def test_two_camera_services(hass, get_data, get_printer_info, get_camera_info):
    double_cam = get_camera_info
    double_cam["webcams"].append(
        {
            "name": "webcam2",
            "stream_url": "/webcam2/?action=stream",
            "snapshot_url": "/webcam2/?action=snapshot",
        }
    )
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **double_cam},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get("camera.mainsail_webcam") is not None
    assert entity_registry.async_get("camera.mainsail_webcam2") is not None


async def test_two_camera_same_name_services(
    hass, get_data, get_printer_info, get_camera_info
):
    double_cam = get_camera_info
    double_cam["webcams"].append(
        {
            "name": "webcam",
            "stream_url": "/webcam/?action=stream",
            "snapshot_url": "/webcam/?action=snapshot",
        }
    )
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info, **double_cam},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        assert await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get("camera.mainsail_webcam") is not None
    assert entity_registry.async_get("camera.mainsail_webcam_2") is not None
