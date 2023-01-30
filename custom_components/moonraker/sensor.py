"""Sensor platform for integration_blueprint."""
from collections.abc import Callable
from dataclasses import dataclass

import logging

from homeassistant.core import callback
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
)
from homeassistant.const import DEGREE, TIME_MINUTES, PERCENTAGE, LENGTH_METERS

from .const import NAME, DOMAIN
from .entity import BaseMoonrakerEntity


_LOGGER = logging.getLogger(__name__)


@dataclass
class MoonrakerSensorDescription(SensorEntityDescription):
    """Class describing Mookraker sensor entities."""

    value_fn: Callable | None = None
    sensor_name: str | None = None
    icon: str | None = None
    unit: str | None = None
    device_class: str | None = None


SENSORS: tuple[MoonrakerSensorDescription, ...] = [
    MoonrakerSensorDescription(
        key="state",
        name="State",
        value_fn=lambda data: data["print_stats"]["state"],
    ),
    MoonrakerSensorDescription(
        key="message",
        name="Message",
        value_fn=lambda data: data["print_stats"]["message"],
    ),
    MoonrakerSensorDescription(
        key="extruder_temp",
        name="Extruder Temperature",
        value_fn=lambda data: float(data["extruder"]["temperature"]),
        icon="mdi:thermometer",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="extruder_target",
        name="Extruder Target",
        value_fn=lambda data: float(data["extruder"]["target"]),
        icon="mdi:thermometer",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="bed_target",
        name="Bed Target",
        value_fn=lambda data: float(data["heater_bed"]["target"]),
        icon="mdi:thermometer",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="bed_temp",
        name="Bed Temperature",
        value_fn=lambda data: float(data["heater_bed"]["temperature"]),
        icon="mdi:thermometer",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="filename",
        name="Filename",
        value_fn=lambda data: data["print_stats"]["filename"],
    ),
    MoonrakerSensorDescription(
        key="print_projected_duration",
        name="print Projected Duration",
        value_fn=lambda data: (
            (data["print_stats"]["print_duration"] / 60)
            / data["display_status"]["progress"]
        )
        if data["display_status"]["progress"] != 0
        else 0,
        icon="mdi:timer",
        unit=TIME_MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="print_eta",
        name="ETA",
        value_fn=lambda data: (
            (
                (data["print_stats"]["print_duration"] / 60)
                / data["display_status"]["progress"]
                if data["display_status"]["progress"] != 0
                else 0
            )
            - data["print_stats"]["print_duration"] / 60
        ),
        icon="mdi:timer",
        unit=TIME_MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="print_duration",
        name="Print Duration",
        value_fn=lambda data: (data["print_stats"]["print_duration"] / 60),
        icon="mdi:timer",
        unit=TIME_MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="filament_used",
        name="Filament Used",
        value_fn=lambda data: int(data["print_stats"]["filament_used"]) * 1.0 / 1000,
        icon="mdi:tape-measure",
        unit=LENGTH_METERS,
    ),
    MoonrakerSensorDescription(
        key="progress",
        name="Progress",
        value_fn=lambda data: int(data["display_status"]["progress"] * 100),
        icon="mdi:percent",
        unit=PERCENTAGE,
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
        self._attr_unique_id = f"{NAME}_{description.key}_123"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self.entity_description = description
        self._attr_native_value = description.value_fn(coordinator.data)
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.unit

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value_fn(
            self.coordinator.data
        )
        self.async_write_ha_state()
