"""Base class entity for Moonraker"""
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class BaseMoonrakerEntity(CoordinatorEntity):
    """Base class entity for Moonraker"""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.api_device_name = coordinator.api_device_name

    @property
    def device_info(self):
        """Entity device info"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.api_device_name,
            model=DOMAIN,
            manufacturer=DOMAIN,
        )


class BaseMoonrakerPushEntity(Entity):
    """Base class push entity for Moonraker"""

    def __init__(self, api_device_name, config_entry):
        super().__init__()
        self.config_entry = config_entry
        self.api_device_name = api_device_name

    @property
    def device_info(self):
        """Entity device info"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id + "push")},
            name=self.api_device_name + "push",
            model=DOMAIN,
            manufacturer=DOMAIN,
        )
