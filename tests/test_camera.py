"""test moonraker camera"""
import datetime as dt
from unittest.mock import patch

from PIL import Image
from homeassistant.components import camera
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.moonraker import async_setup_entry
from custom_components.moonraker.const import DOMAIN, PRINTSTATES

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_camera_services(hass):
    """Test camera services"""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("camera.mainsail_webcam")

    assert entry is not None


async def test_two_cameras_services(hass, get_camera_info):
    """Test cameras Services"""
    get_camera_info["webcams"].append(
        {
            "name": "webcam2",
            "stream_url": "/webcam2/?action=stream",
            "snapshot_url": "/webcam2/?action=snapshot",
        }
    )

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get("camera.mainsail_webcam") is not None
    assert entity_registry.async_get("camera.mainsail_webcam2") is not None


async def test_two_cameras_same_name_services(hass, get_camera_info):
    """Test two cameras same name"""
    get_camera_info["webcams"].append(
        {
            "name": "webcam",
            "stream_url": "/webcam/?action=stream",
            "snapshot_url": "/webcam/?action=snapshot",
        }
    )

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get("camera.mainsail_webcam") is not None
    assert entity_registry.async_get("camera.mainsail_webcam_2") is not None


async def test_setup_thumbnail_camera(hass, get_data):
    """Test setup thumbnail camera"""
    get_data["status"]["print_stats"]["filename"] = "CE3E3V2_picture_frame_holder.gcode"

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("camera.mainsail_thumbnail")

    assert entry is not None


async def test_thumbnail_camera_image(hass, aioclient_mock, get_data):
    """Test thumbnail camera image"""

    get_data["status"]["print_stats"]["filename"] = "CE3E3V2_picture_frame_holder.gcode"

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    test_path = (
        "http://1.2.3.4/server/files/gcodes/.thumbs/CE3E3V2_picture_frame_holder.png"
    )

    aioclient_mock.get(test_path, content=Image.new("RGB", (30, 30)))

    await camera.async_get_image(hass, "camera.mainsail_thumbnail")
    await camera.async_get_image(hass, "camera.mainsail_thumbnail")


async def test_thumbnail_camera_from_img_to_none(hass):
    """Test thumbnail camera from img to none"""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    with pytest.raises(Exception):
        await camera.async_get_image(hass, "camera.mainsail_thumbnail")


async def test_thumbnail_no_thumbnail(hass, get_data):
    """Test setup thumbnail camera"""
    get_data["status"]["print_stats"]["filename"] = ""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("camera.mainsail_thumbnail")

    assert entry is not None


async def test_thumbnail_not_printing(hass, aioclient_mock, get_data):
    """Test setup thumbnail camera"""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    test_path = (
        "http://1.2.3.4/server/files/gcodes/.thumbs/CE3E3V2_picture_frame_holder.png"
    )

    aioclient_mock.get(test_path, content=Image.new("RGB", (30, 30)))

    with pytest.raises(Exception):
        await camera.async_get_image(hass, "camera.mainsail_thumbnail")


async def test_thumbnail_no_thumbnail_after_update(
    hass,
    aioclient_mock,
    get_data,
):
    """Test setup thumbnail camera"""

    get_data["status"]["print_stats"]["filename"] = "CE3E3V2_picture_frame_holder.gcode"

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    test_path = (
        "http://1.2.3.4/server/files/gcodes/.thumbs/CE3E3V2_picture_frame_holder.png"
    )

    aioclient_mock.get(test_path, content=Image.new("RGB", (30, 30)))

    await camera.async_get_image(hass, "camera.mainsail_thumbnail")

    get_data["status"]["print_stats"]["filename"] = ""

    async_fire_time_changed(
        hass,
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
    )
    await hass.async_block_till_done()

    with pytest.raises(Exception):
        await camera.async_get_image(hass, "camera.mainsail_thumbnail")


async def test_thumbnail_data_failing(hass, aioclient_mock, get_data):
    """Test setup thumbnail camera"""

    get_data["status"]["print_stats"]["filename"] = "CE3E3V2_picture_frame_holder.gcode"
    del get_data["thumbnails"]

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("camera.mainsail_thumbnail")

    assert entry is not None
