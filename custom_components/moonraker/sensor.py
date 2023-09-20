"""Sensor platform for Moonraker integration."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfTemperature, UnitOfTime
from homeassistant.core import callback

from .const import DOMAIN, METHODS, PRINTERSTATES, PRINTSTATES
from .entity import BaseMoonrakerEntity

_LOGGER = logging.getLogger(__name__)


@dataclass
class MoonrakerSensorDescription(SensorEntityDescription):
    """Class describing Mookraker sensor entities."""

    value_fn: Callable | None = None
    sensor_name: str | None = None
    status_key: str | None = None
    icon: str | None = None
    unit: str | None = None
    device_class: str | None = None
    subscriptions: list | None = None


SENSORS: tuple[MoonrakerSensorDescription, ...] = [
    MoonrakerSensorDescription(
        key="state",
        name="Printer State",
        value_fn=lambda sensor: sensor.coordinator.data["printer.info"]["state"],
        device_class=SensorDeviceClass.ENUM,
        options=PRINTERSTATES.list(),
        subscriptions=[],
    ),
    MoonrakerSensorDescription(
        key="message",
        name="Printer Message",
        value_fn=lambda sensor: sensor.coordinator.data["printer.info"][
            "state_message"
        ],
        subscriptions=[],
    ),
    MoonrakerSensorDescription(
        key="print_state",
        name="Current Print State",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["print_stats"][
            "state"
        ],
        device_class=SensorDeviceClass.ENUM,
        options=PRINTSTATES.list(),
        subscriptions=[("print_stats", "state")],
    ),
    MoonrakerSensorDescription(
        key="print_message",
        name="Current Print Message",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["print_stats"][
            "message"
        ],
        subscriptions=[("print_stats", "message")],
    ),
    MoonrakerSensorDescription(
        key="display_message",
        name="Current Display Message",
        value_fn=lambda sensor: sensor.coordinator.data["status"]["display_status"][
            "message"
        ]
        if sensor.coordinator.data["status"]["display_status"]["message"] is not None
        else "",
        subscriptions=[("display_status", "message")],
    ),
    MoonrakerSensorDescription(
        key="extruder_temp",
        name="Extruder Temperature",
        value_fn=lambda sensor: float(
            sensor.coordinator.data["status"]["extruder"]["temperature"]
        ),
        subscriptions=[("extruder", "temperature")],
        icon="mdi:printer-3d-nozzle-heat",
        unit=UnitOfTemperature.CELSIUS,
    ),
    MoonrakerSensorDescription(
        key="extruder_target",
        name="Extruder Target",
        value_fn=lambda sensor: float(
            sensor.coordinator.data["status"]["extruder"]["target"]
        ),
        subscriptions=[("extruder", "target")],
        icon="mdi:printer-3d-nozzle-heat",
        unit=UnitOfTemperature.CELSIUS,
    ),
    MoonrakerSensorDescription(
        key="bed_target",
        name="Bed Target",
        value_fn=lambda sensor: float(
            sensor.coordinator.data["status"]["heater_bed"]["target"]
        ),
        subscriptions=[("heater_bed", "target")],
        icon="mdi:radiator",
        unit=UnitOfTemperature.CELSIUS,
    ),
    MoonrakerSensorDescription(
        key="bed_temp",
        name="Bed Temperature",
        value_fn=lambda sensor: float(
            sensor.coordinator.data["status"]["heater_bed"]["temperature"]
        ),
        subscriptions=[("heater_bed", "temperature")],
        icon="mdi:radiator",
        unit=UnitOfTemperature.CELSIUS,
    ),
    MoonrakerSensorDescription(
        key="filename",
        name="Filename",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["status"]["print_stats"]["filename"]
        ),
        subscriptions=[("print_stats", "filename")],
    ),
    MoonrakerSensorDescription(
        key="print_projected_total_duration",
        name="print Projected Total Duration",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            round(
                sensor.coordinator.data["status"]["print_stats"]["print_duration"]
                / calculate_pct_job(sensor.coordinator.data)
                if calculate_pct_job(sensor.coordinator.data) != 0
                else 0,
                2,
            )
        ),
        subscriptions=[
            ("print_stats", "total_duration"),
            ("display_status", "progress"),
        ],
        icon="mdi:timer",
        unit=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="print_time_left",
        name="Print Time Left",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            round(
                (
                    sensor.coordinator.data["status"]["print_stats"]["print_duration"]
                    / calculate_pct_job(sensor.coordinator.data)
                    if calculate_pct_job(sensor.coordinator.data) != 0
                    else 0
                )
                - sensor.coordinator.data["status"]["print_stats"]["print_duration"],
                2,
            )
        ),
        subscriptions=[
            ("print_stats", "print_duration"),
            ("display_status", "progress"),
        ],
        icon="mdi:timer",
        unit=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="print_eta",
        name="Print ETA",
        value_fn=lambda sensor: calculate_eta(sensor.coordinator.data),
        subscriptions=[
            ("print_stats", "print_duration"),
            ("display_status", "progress"),
        ],
        icon="mdi:timer",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    MoonrakerSensorDescription(
        key="slicer_print_duration_estimate",
        name="Slicer Print Duration Estimate",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["estimated_time"]
        ),
        subscriptions=[],
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        unit=UnitOfTime.SECONDS,
    ),
    MoonrakerSensorDescription(
        key="slicer_print_time_left_estimate",
        name="Slicer Print Time Left Estimate",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["estimated_time"]
            - sensor.coordinator.data["status"]["print_stats"]["print_duration"]
        ),
        subscriptions=[("print_stats", "print_duration")],
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        unit=UnitOfTime.SECONDS,
    ),
    MoonrakerSensorDescription(
        key="print_duration",
        name="Print Duration",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            round(
                sensor.coordinator.data["status"]["print_stats"]["print_duration"] / 60,
                2,
            )
        ),
        subscriptions=[("print_stats", "print_duration")],
        icon="mdi:timer",
        unit=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    MoonrakerSensorDescription(
        key="filament_used",
        name="Filament Used",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            round(
                int(sensor.coordinator.data["status"]["print_stats"]["filament_used"])
                * 1.0
                / 1000,
                2,
            )
        ),
        subscriptions=[("print_stats", "filament_used")],
        icon="mdi:tape-measure",
        unit=UnitOfLength.METERS,
    ),
    MoonrakerSensorDescription(
        key="progress",
        name="Progress",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            int(sensor.coordinator.data["status"]["display_status"]["progress"] * 100)
        ),
        subscriptions=[("display_status", "progress")],
        icon="mdi:percent",
        unit=PERCENTAGE,
    ),
    MoonrakerSensorDescription(
        key="bed_power",
        name="Bed Power",
        value_fn=lambda sensor: int(
            sensor.coordinator.data["status"]["heater_bed"]["power"] * 100
        ),
        subscriptions=[("heater_bed", "power")],
        icon="mdi:flash",
        unit=PERCENTAGE,
    ),
    MoonrakerSensorDescription(
        key="extruder_power",
        name="Extruder Power",
        value_fn=lambda sensor: int(
            sensor.coordinator.data["status"]["extruder"]["power"] * 100
        ),
        subscriptions=[("extruder", "power")],
        icon="mdi:flash",
        unit=PERCENTAGE,
    ),
    MoonrakerSensorDescription(
        key="total_layer",
        name="Total Layer",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["layer_count"]
        ),
        subscriptions=[("print_stats", "info", "total_layer")],
        icon="mdi:layers-triple",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MoonrakerSensorDescription(
        key="current_layer",
        name="Current Layer",
        value_fn=lambda sensor: calculate_current_layer(sensor.coordinator.data),
        subscriptions=[("print_stats", "info", "current_layer")],
        icon="mdi:layers-edit",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MoonrakerSensorDescription(
        key="toolhead_position_x",
        name="Toolhead position X",
        value_fn=lambda sensor: round(
            sensor.coordinator.data["status"]["toolhead"]["position"][0], 2
        ),
        subscriptions=[("toolhead", "position")],
        icon="mdi:axis-x-arrow",
        unit=UnitOfLength.MILLIMETERS,
    ),
    MoonrakerSensorDescription(
        key="toolhead_position_y",
        name="Toolhead position Y",
        value_fn=lambda sensor: round(
            sensor.coordinator.data["status"]["toolhead"]["position"][1], 2
        ),
        subscriptions=[("toolhead", "position")],
        icon="mdi:axis-y-arrow",
        unit=UnitOfLength.MILLIMETERS,
    ),
    MoonrakerSensorDescription(
        key="toolhead_position_z",
        name="Toolhead position Z",
        value_fn=lambda sensor: round(
            sensor.coordinator.data["status"]["toolhead"]["position"][2], 2
        ),
        subscriptions=[("toolhead", "position")],
        icon="mdi:axis-z-arrow",
        unit=UnitOfLength.MILLIMETERS,
    ),
    MoonrakerSensorDescription(
        key="object_height",
        name="Object Height",
        value_fn=lambda sensor: sensor.empty_result_when_not_printing(
            sensor.coordinator.data["object_height"]
        ),
        subscriptions=[],
        icon="mdi:axis-z-arrow",
        device_class=SensorDeviceClass.DISTANCE,
        unit=UnitOfLength.MILLIMETERS,
    ),
]


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    await async_setup_basic_sensor(coordinator, entry, async_add_entities)
    await async_setup_optional_sensors(coordinator, entry, async_add_entities)
    await async_setup_history_sensors(coordinator, entry, async_add_entities)


async def async_setup_basic_sensor(coordinator, entry, async_add_entities):
    """Setup basic sensor platform."""
    coordinator.load_sensor_data(SENSORS)
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in SENSORS])


async def async_setup_optional_sensors(coordinator, entry, async_add_entities):
    """Setup optional sensor platform."""

    temperature_keys = [
        "temperature_sensor",
        "temperature_fan",
        "bme280",
        "htu21d",
        "lm75",
    ]

    fan_keys = ["heater_fan", "controller_fan", "fan_generic"]

    sensors = []
    object_list = await coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)
    for obj in object_list["objects"]:
        split_obj = obj.split()

        if split_obj[0] in temperature_keys:
            desc = MoonrakerSensorDescription(
                key=f"{split_obj[0]}_{split_obj[1]}",
                status_key=obj,
                name=split_obj[1].replace("_", " ").title(),
                value_fn=lambda sensor: sensor.coordinator.data["status"][
                    sensor.status_key
                ]["temperature"],
                subscriptions=[(obj, "temperature")],
                icon="mdi:thermometer",
                unit=UnitOfTemperature.CELSIUS,
            )
            sensors.append(desc)
        elif split_obj[0] in fan_keys:
            desc = MoonrakerSensorDescription(
                key=f"{split_obj[0]}_{split_obj[1]}",
                status_key=obj,
                name=split_obj[1].replace("_", " ").title(),
                value_fn=lambda sensor: sensor.coordinator.data["status"][
                    sensor.status_key
                ]["speed"]
                * 100,
                subscriptions=[(obj, "speed")],
                icon="mdi:fan",
                unit=PERCENTAGE,
            )
            sensors.append(desc)
        elif obj == "fan":
            desc = MoonrakerSensorDescription(
                key="fan_speed",
                name="Fan speed",
                value_fn=lambda sensor: round(
                    sensor.coordinator.data["status"]["fan"]["speed"] * 100, 2
                ),
                subscriptions=[("fan", "speed")],
                icon="mdi:fan",
                unit=PERCENTAGE,
            )
            sensors.append(desc)
        elif obj == "gcode_move":
            desc = MoonrakerSensorDescription(
                key="speed_factor",
                name="Speed factor",
                value_fn=lambda sensor: round(
                    sensor.coordinator.data["status"]["gcode_move"]["speed_factor"] * 100, 2
                ),
                subscriptions=[("gcode_move", "speed_factor")],
                icon="mdi:speedometer",
                unit=PERCENTAGE,
            )
            sensors.append(desc)

    coordinator.load_sensor_data(sensors)
    await coordinator.async_refresh()
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in sensors])


async def _history_updater(coordinator):
    return {
        "history": await coordinator.async_fetch_data(METHODS.SERVER_HISTORY_TOTALS)
    }


async def async_setup_history_sensors(coordinator, entry, async_add_entities):
    history = await coordinator.async_fetch_data(METHODS.SERVER_HISTORY_TOTALS)
    if history.get("error"):
        return

    coordinator.add_data_updater(_history_updater)

    sensors = [
        MoonrakerSensorDescription(
            key="total_jobs",
            name="Totals jobs",
            value_fn=lambda sensor: sensor.coordinator.data["history"]["job_totals"][
                "total_jobs"
            ],
            subscriptions=[],
            icon="mdi:numeric",
            unit="Jobs",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        MoonrakerSensorDescription(
            key="total_print_time",
            name="Totals Print Time",
            value_fn=lambda sensor: convert_time(
                sensor.coordinator.data["history"]["job_totals"]["total_print_time"]
            ),
            subscriptions=[],
            icon="mdi:clock-outline",
        ),
        MoonrakerSensorDescription(
            key="total_filament_used",
            name="Totals Filament Used",
            value_fn=lambda sensor: round(
                sensor.coordinator.data["history"]["job_totals"]["total_filament_used"]
                / 1000,
                2,
            ),
            subscriptions=[],
            icon="mdi:clock-outline",
            unit=UnitOfLength.METERS,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        MoonrakerSensorDescription(
            key="longest_print",
            name="Longest Print",
            value_fn=lambda sensor: convert_time(
                sensor.coordinator.data["history"]["job_totals"]["longest_print"]
            ),
            subscriptions=[],
            icon="mdi:clock-outline",
        ),
    ]

    coordinator.load_sensor_data(sensors)
    await coordinator.async_refresh()
    async_add_entities([MoonrakerSensor(coordinator, entry, desc) for desc in sensors])


class MoonrakerSensor(BaseMoonrakerEntity, SensorEntity):
    """MoonrakerSensor Sensor class."""

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator, entry)
        self.coordinator = coordinator
        self.status_key = description.status_key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self.entity_description = description
        self._attr_native_value = description.value_fn(self)
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.unit

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.entity_description.value_fn(self)
        self.async_write_ha_state()

    def empty_result_when_not_printing(self, value=""):
        """Return empty string when not printing"""
        if (
            self.coordinator.data["status"]["print_stats"]["state"]
            != PRINTSTATES.PRINTING.value
        ):
            return "" if isinstance(value, str) else 0.0
        return value


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
    percent_job = calculate_pct_job(data)
    if (
        data["status"]["print_stats"]["print_duration"] <= 0
        or percent_job <= 0
        or percent_job >= 1
    ):
        return None

    time_left = round(
        (data["status"]["print_stats"]["print_duration"] / percent_job)
        - data["status"]["print_stats"]["print_duration"],
        2,
    )

    return datetime.now(timezone.utc) + timedelta(0, time_left)


def calculate_current_layer(data):
    """Calculate current layer"""

    if (
        data["status"]["print_stats"]["state"] != PRINTSTATES.PRINTING.value
        or data["status"]["print_stats"]["filename"] == ""
    ):
        return 0

    if (
        "info" in data["status"]["print_stats"]
        and data["status"]["print_stats"]["info"] is not None
        and "current_layer" in data["status"]["print_stats"]["info"]
        and data["status"]["print_stats"]["info"]["current_layer"] is not None
    ):
        return data["status"]["print_stats"]["info"]["current_layer"]

    # layer = (current_z - first_layer_height) / layer_height + 1
    return (
        int(
            round(
                (data["status"]["toolhead"]["position"][2] - data["first_layer_height"])
                / data["layer_height"],
                0,
            )
        )
        + 1
    )


def convert_time(time_s):
    """Convert time in seconds to a human readable string"""
    return (
        f"{round(time_s // 3600)}h {round(time_s % 3600 // 60)}m {round(time_s % 60)}s"
    )
