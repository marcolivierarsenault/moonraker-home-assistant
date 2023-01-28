"""Sensor platform for integration_blueprint."""
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.core import callback
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription

from .const import NAME, DOMAIN
from .entity import BaseMoonrakerEntity


@dataclass
class MoonrakerSensorDescription(SensorEntityDescription):
    """Class describing Mookraker sensor entities."""

    value_fn: Callable | None = None
    sensor_name: str | None = None


SENSORS: tuple[MoonrakerSensorDescription, ...] = [
    MoonrakerSensorDescription(
        key="state",
        name="State",
        value_fn=lambda data: data["print_stats"]["state"],
    ),
    MoonrakerSensorDescription(
        key="filename",
        name="Filename",
        value_fn=lambda data: data["print_stats"]["filename"],
    ),
]


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [MoonrakerSensor(coordinator, entry, description) for description in SENSORS]
    )


class MoonrakerSensor(BaseMoonrakerEntity, SensorEntity):
    """MoonrakerSensor Sensor class."""

    def __init__(self, coordinator, entry, description):

        super().__init__(coordinator, entry)
        self.coordinator = coordinator
        self._attr_name = f"{description.name}"
        self.entity_description = description
        self._attr_native_value = description.value_fn(coordinator.data)
        self._attr_unique_id = f"{NAME}_sensor_{description.name}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value_fn(
            self.coordinator.data
        )
        self.async_write_ha_state()
