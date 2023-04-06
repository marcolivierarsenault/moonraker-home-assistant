"""Switch platform for Moonraker integration."""
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .const import DOMAIN, METHODS
from .entity import BaseMoonrakerEntity


@dataclass
class MoonrakerSwitchSensorDescription(SwitchEntityDescription):
    """Class describing Mookraker binary_sensor entities."""

    sensor_name: str | None = None
    icon: str | None = None
    subscriptions: list | None = None


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    await async_setup_power_device(coordinator, entry, async_add_devices)


async def _power_device_updater(coordinator):
    return {
        "power_devices": await coordinator.async_fetch_data(
            METHODS.MACHINE_DEVICE_POWER_DEVICES
        )
    }


async def async_setup_power_device(coordinator, entry, async_add_entities):
    """Setup optional binary sensor platform."""

    power_devices = await coordinator.async_fetch_data(
        METHODS.MACHINE_DEVICE_POWER_DEVICES
    )
    if power_devices.get("error"):
        return

    coordinator.add_data_updater(_power_device_updater)

    sensors = []
    for device in power_devices["devices"]:
        desc = MoonrakerSwitchSensorDescription(
            key=device["device"],
            sensor_name=device["device"],
            name=device["device"].replace("_", " ").title(),
            icon="mdi:power",
            subscriptions=[],
        )
        sensors.append(desc)

    coordinator.load_sensor_data(sensors)
    await coordinator.async_refresh()
    async_add_entities(
        [MoonrakerSwitchSensor(coordinator, entry, desc) for desc in sensors]
    )


class MoonrakerSwitchSensor(BaseMoonrakerEntity, SwitchEntity):
    """Moonraker switch class."""

    def __init__(
        self,
        coordinator,
        entry,
        description,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self._attr_icon = description.icon

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        for device in self.coordinator.data["power_devices"]["devices"]:
            if device["device"] == self.sensor_name:
                return device["status"] == "on"

    async def async_turn_on(self, **_: any) -> None:
        """Turn on the switch."""
        await self.coordinator.async_send_data(
            METHODS.MACHINE_DEVICE_POWER_POST_DEVICE,
            {"device": self.sensor_name, "action": "on"},
        )
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **_: any) -> None:
        """Turn off the switch."""
        await self.coordinator.async_send_data(
            METHODS.MACHINE_DEVICE_POWER_POST_DEVICE,
            {"device": self.sensor_name, "action": "off"},
        )
        await self.coordinator.async_refresh()
