"""Support for Moonraker camera."""
from __future__ import annotations

import logging

from homeassistant.components.camera import Camera
from homeassistant.components.mjpeg.camera import MjpegCamera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_URL, DOMAIN, METHODS, PRINTSTATES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Moonraker camera."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    cameras = await coordinator.async_fetch_data(METHODS.SERVER_WEBCAMS_LIST)

    for camera_id, camera in enumerate(cameras["webcams"]):
        async_add_entities(
            [MoonrakerCamera(config_entry, coordinator, camera, camera_id)]
        )

    async_add_entities(
        [
            PreviewCamera(
                config_entry,
                coordinator,
                async_get_clientsession(hass, verify_ssl=False),
            )
        ]
    )


class MoonrakerCamera(MjpegCamera):
    """Representation of an Moonraker Camera Stream."""

    def __init__(self, config_entry, coordinator, camera, camera_id) -> None:
        """Initialize as a subclass of MjpegCamera."""

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}
        )
        if camera["stream_url"].startswith("http"):
            self.url = ""
        else:
            self.url = f"http://{config_entry.data.get(CONF_URL)}"

        _LOGGER.info(f"Connecting to camera: {self.url}{camera['stream_url']}")

        super().__init__(
            device_info=self._attr_device_info,
            mjpeg_url=f"{self.url}{camera['stream_url']}",
            name=f"{coordinator.api_device_name} {camera['name']}",
            still_image_url=f"{self.url}{camera['snapshot_url']}",
            unique_id=f"{config_entry.entry_id}_{camera['name']}_{camera_id}",
        )


class PreviewCamera(Camera):
    """Representation of the gcode thumnail."""

    _attr_is_streaming = False

    def __init__(self, config_entry, coordinator, session) -> None:
        """Initialize as a subclass of Camera for the Thumbnail Preview"""

        super().__init__()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}
        )
        self.url = config_entry.data.get(CONF_URL)
        self.coordinator = coordinator
        self._attr_name = f"{coordinator.api_device_name} Thumbnail"
        self._attr_unique_id = f"{config_entry.entry_id}_thumbnail"
        self._session = session
        self._current_pic = None
        self._current_path = ""

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return current camera image"""
        if (
            self.coordinator.data["status"]["print_stats"]["state"]
            != PRINTSTATES.PRINTING.value
        ):
            return None

        del width, height

        new_path = self.coordinator.data["thumbnails_path"]
        if self._current_path == new_path and self._current_pic is not None:
            return self._current_pic

        if new_path == "" or new_path is None:
            self._current_pic = None
            self._current_path = ""
            return None
        response = await self._session.get(
            f"http://{self.url}/server/files/gcodes/{new_path}"
        )

        self._current_path = new_path
        self._current_pic = await response.read()

        return self._current_pic
