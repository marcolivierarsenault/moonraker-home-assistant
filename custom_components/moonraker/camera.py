"""Support for OctoPrint binary camera."""
from __future__ import annotations

from homeassistant.components.mjpeg.camera import MjpegCamera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_URL


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Moonraker camera."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities([MoonrakerCamera(config_entry, coordinator)])


class MoonrakerCamera(MjpegCamera):
    """Representation of an Moonraker Camera Stream."""

    def __init__(self, config_entry, coordinator) -> None:
        """Initialize as a subclass of MjpegCamera."""

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}
        )
        self.url = config_entry.data.get(CONF_URL)
        super().__init__(
            device_info=self._attr_device_info,
            mjpeg_url=f"http://{self.url}/webcam/?action=stream",
            name="Moonraker Camera",
            still_image_url=f"http://{self.url}/webcam/?action=snapshot",
            unique_id=f"{coordinator.api_device_name}_camera",
        )
