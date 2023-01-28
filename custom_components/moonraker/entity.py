"""Base class entity for Moonraker"""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, NAME


class BaseMoonrakerEntity(CoordinatorEntity):
    """Base class entity for Moonraker"""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=NAME,
            manufacturer=NAME,
            model=NAME,
        )
