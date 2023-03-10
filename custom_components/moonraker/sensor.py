"""Sensor platform for integration_blueprint."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import DEGREE, LENGTH_METERS, PERCENTAGE, TIME_SECONDS
from homeassistant.core import callback

from .const import DOMAIN
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
    subscriptions: list | None = None


SENSORS: tuple[MoonrakerSensorDescription, ...] = [
    MoonrakerSensorDescription(
        key="state",
        name="Printer State",
        value_fn=lambda data: data["printer.info"]["state"],
        subscriptions=[],
    ),
    MoonrakerSensorDescription(
        key="message",
        name="Printer Message",
        value_fn=lambda data: data["printer.info"]["state_message"],
        subscriptions=[],
    ),
    MoonrakerSensorDescription(
        key="print_state",
        name="Current Print State",
        value_fn=lambda data: data["status"]["print_stats"]["state"],
        subscriptions=[("print_stats", "state")],
    ),
    MoonrakerSensorDescription(
        key="print_message",
        name="Current Print Message",
        value_fn=lambda data: data["status"]["print_stats"]["message"],
        subscriptions=[("print_stats", "message")],
    ),
    MoonrakerSensorDescription(
        key="display_message",
        name="Current Display Message",
        value_fn=lambda data: data["status"]["display_status"]["message"]
        if data["status"]["display_status"]["message"] is not None
        else "",
        subscriptions=[("display_status", "message")],
    ),
    MoonrakerSensorDescription(
        key="extruder_temp",
        name="Extruder Temperature",
        value_fn=lambda data: float(data["status"]["extruder"]["temperature"]),
        subscriptions=[("extruder", "temperature")],
        icon="mdi:printer-3d-nozzle-heat",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="extruder_target",
        name="Extruder Target",
        value_fn=lambda data: float(data["status"]["extruder"]["target"]),
        subscriptions=[("extruder", "target")],
        icon="mdi:printer-3d-nozzle-heat",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="bed_target",
        name="Bed Target",
        value_fn=lambda data: float(data["status"]["heater_bed"]["target"]),
        subscriptions=[("heater_bed", "target")],
        icon="mdi:radiator",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="bed_temp",
        name="Bed Temperature",
        value_fn=lambda data: float(data["status"]["heater_bed"]["temperature"]),
        subscriptions=[("heater_bed", "temperature")],
        icon="mdi:radiator",
        unit=DEGREE,
    ),
    MoonrakerSensorDescription(
        key="filename",
        name="Filename",
        value_fn=lambda data: data["status"]["print_stats"]["filename"],
        subscriptions=[("print_stats", "filename")],
    ),
    MoonrakerSensorDescription(
        key="print_projected_total_duration",
        name="print Projected Total Duration",
        value_fn=lambda data: round(
            data["status"]["print_stats"]["print_duration"] / calculate_pct_job(data)
            if calculate_pct_job(data) != 0
            else 0,
            2,
        ),
        subscriptions=[
            ("print_stats", "total_duration"),
            ("display_status", "progress"),
        ],
        icon="mdi:timer",
        unit=TIME_SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="print_time_left",
        name="Print Time Left",
        value_fn=lambda data: round(
            (
                data["status"]["print_stats"]["print_duration"]
                / calculate_pct_job(data)
                if calculate_pct_job(data) != 0
                else 0
            )
            - data["status"]["print_stats"]["print_duration"],
            2,
        ),
        subscriptions=[
            ("print_stats", "print_duration"),
            ("display_status", "progress"),
        ],
        icon="mdi:timer",
        unit=TIME_SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="print_eta",
        name="Print ETA",
        value_fn=lambda data: calculate_eta(data),
        subscriptions=[
            ("print_stats", "print_duration"),
            ("display_status", "progress"),
        ],
        icon="mdi:timer",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    MoonrakerSensorDescription(
        key="print_duration",
        name="Print Duration",
        value_fn=lambda data: round(
            data["status"]["print_stats"]["print_duration"] / 60, 2
        ),
        subscriptions=[("print_stats", "print_duration")],
        icon="mdi:timer",
        unit=TIME_SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="filament_used",
        name="Filament Used",
        value_fn=lambda data: round(
            int(data["status"]["print_stats"]["filament_used"]) * 1.0 / 1000, 2
        ),
        subscriptions=[("print_stats", "filament_used")],
        icon="mdi:tape-measure",
        unit=LENGTH_METERS,
    ),
    MoonrakerSensorDescription(
        key="progress",
        name="Progress",
        value_fn=lambda data: int(data["status"]["display_status"]["progress"] * 100),
        subscriptions=[("display_status", "progress")],
        icon="mdi:percent",
        unit=PERCENTAGE,
    ),
    MoonrakerSensorDescription(
        key="bed_power",
        name="Bed Power",
        value_fn=lambda data: int(data["status"]["heater_bed"]["power"] * 100),
        subscriptions=[("heater_bed", "power")],
        icon="mdi:flash",
        unit=PERCENTAGE,
    ),
    MoonrakerSensorDescription(
        key="extruder_power",
        name="Extruder Power",
        value_fn=lambda data: int(data["status"]["extruder"]["power"] * 100),
        subscriptions=[("extruder", "power")],
        icon="mdi:flash",
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
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
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


def calculate_pct_job(data) -> float:
    """
    Get a pct estimate of the job based on a mix of progress value and fillament used.
    This strategy is inline with Mainsail estimate
    """
    print_expected_duration = data["estimated_time"]
    filament_used = data["status"]["print_stats"]["filament_used"]
    expected_filament = data["filament_total"]
    if print_expected_duration == 0 or expected_filament == 0:
        return 0

    time_pct = data["status"]["display_status"]["progress"]
    filament_pct = 1.0 * filament_used / expected_filament

    return (time_pct + filament_pct) / 2


def calculate_eta(data):
    """Calculate ETA of current print"""
    if (
        data["status"]["print_stats"]["print_duration"] <= 0
        or calculate_pct_job(data) <= 0
    ):
        return None

    time_left = round(
        (data["status"]["print_stats"]["print_duration"] / calculate_pct_job(data))
        - data["status"]["print_stats"]["print_duration"],
        2,
    )

    return datetime.now(timezone.utc) + timedelta(0, time_left)
