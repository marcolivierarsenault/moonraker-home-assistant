"""Number platform for Moonraker integration."""

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberDeviceClass,
    NumberMode,
)
from homeassistant.core import callback
from homeassistant.const import UnitOfTemperature, PERCENTAGE

from .const import DOMAIN, METHODS, OBJ
from .entity import BaseMoonrakerEntity
from custom_components.moonraker.__init__ import MoonrakerDataUpdateCoordinator


@dataclass(frozen=True)
class MoonrakerNumberSensorDescription(NumberEntityDescription):
    """Class describing Mookraker number entities."""

    sensor_name: str | None = None
    subscriptions: list | None = None
    icon: str | None = None
    unit: str | None = None
    update_code: str | None = None
    max_value: float | None = None
    min_value: float | None = None
    device_class: NumberDeviceClass | None = None
    status_key: str | None = None


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the number platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    await async_setup_output_pin(coordinator, entry, async_add_devices)
    await async_setup_temperature_target(coordinator, entry, async_add_devices)
    await async_setup_speed_factor(coordinator, entry, async_add_devices)
    await async_setup_fan_speed(coordinator, entry, async_add_devices)


async def async_setup_temperature_target(coordinator, entry, async_add_entities):
    """Set optional temp target."""

    sensors = []

    config_query = {OBJ: {"configfile": ["settings"]}}
    config_response = await coordinator.async_fetch_data(
        METHODS.PRINTER_OBJECTS_QUERY, config_query, quiet=True
    )
    config_settings = config_response["status"]["configfile"].get("settings", {})

    object_list = await coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)
    for obj in object_list["objects"]:
        if obj.startswith("heater_bed"):
            desc = MoonrakerNumberSensorDescription(
                key=f"{obj}_target",
                sensor_name=obj,
                name="Bed Target".title(),
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:radiator",
                unit=UnitOfTemperature.CELSIUS,
                update_code="M140 S",
                max_value=130,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)

        elif obj.startswith("extruder"):
            extruder_val = "0" if obj == "extruder" else obj[-1]

            desc = MoonrakerNumberSensorDescription(
                key=f"{obj}_target",
                sensor_name=obj,
                name=f"{obj} Target".title(),
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:printer-3d-nozzle-heat",
                unit=UnitOfTemperature.CELSIUS,
                update_code=f"M104 T{extruder_val} S",
                max_value=350,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)

        elif obj.startswith("heater_generic"):
            _, _, heater_name = obj.partition(" ")
            display_name = heater_name.replace("_", " ").title() if heater_name else "Heater Generic"

            settings = config_settings.get(obj)
            if settings is None:
                settings = config_settings.get(obj.lower())
            if settings is None:
                settings = {}

            max_temp = settings.get("max_temp")
            min_temp = settings.get("min_temp")

            desc = MoonrakerNumberSensorDescription(
                key=f"{obj.replace(' ', '_')}_target_number",
                sensor_name=obj,
                name=f"{display_name} Target",
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:radiator",
                unit=UnitOfTemperature.CELSIUS,
                update_code=f"SET_HEATER_TEMPERATURE HEATER={heater_name or 'heater_generic'} TARGET=",
                max_value=float(max_temp) if max_temp is not None else None,
                min_value=float(min_temp) if min_temp is not None else 0.0,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)
            coordinator.add_query_objects(obj, "target")

        elif obj.startswith("temperature_fan"):
            object_type, _, object_name = obj.partition(" ")
            fan_name = object_name or object_type
            fan_key = fan_name.replace(" ", "_")
            display_name = fan_name.replace("_", " ").title()

            settings = config_settings.get(obj)
            if settings is None:
                lower_obj = obj.lower()
                settings = config_settings.get(lower_obj)
            if settings is None:
                settings = {}

            max_temp = settings.get("max_temp")
            min_temp = settings.get("min_temp")

            max_value = float(max_temp) if max_temp is not None else 100.0
            min_value = float(min_temp) if min_temp is not None else 0.0

            desc = MoonrakerNumberSensorDescription(
                key=f"{object_type}_{fan_key}_target_control",
                sensor_name=obj,
                name=f"{display_name} Target",
                status_key="target",
                subscriptions=[(obj, "target")],
                icon="mdi:thermometer",
                unit=UnitOfTemperature.CELSIUS,
                update_code=f"SET_TEMPERATURE_FAN_TARGET FAN={fan_name} TARGET=",
                max_value=max_value,
                min_value=min_value,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
            sensors.append(desc)
            coordinator.add_query_objects(obj, "target")

    coordinator.load_sensor_data(sensors)
    await coordinator.async_refresh()
    async_add_entities([MoonrakerNumber(coordinator, entry, desc) for desc in sensors])


async def async_setup_output_pin(coordinator, entry, async_add_entities):
    """Set optional binary sensor platform."""

    object_list = await coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)

    query_obj = {OBJ: {"configfile": ["settings"]}}
    settings = await coordinator.async_fetch_data(
        METHODS.PRINTER_OBJECTS_QUERY, query_obj, quiet=True
    )

    numbers = []
    for obj in object_list["objects"]:
        if "output_pin" not in obj:
            continue

        if not settings["status"]["configfile"]["settings"][obj.lower()]["pwm"]:
            continue

        desc = MoonrakerNumberSensorDescription(
            key=obj,
            sensor_name=obj,
            name=obj.replace("_", " ").title(),
            icon="mdi:switch",
            subscriptions=[(obj, "value")],
        )
        numbers.append(desc)

    coordinator.load_sensor_data(numbers)
    await coordinator.async_refresh()
    async_add_entities(
        [MoonrakerPWMOutputPin(coordinator, entry, desc) for desc in numbers]
    )


async def async_setup_speed_factor(coordinator, entry, async_add_entities):
    """Set up speed factor number entity."""

    object_list = await coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)
    if "gcode_move" not in object_list["objects"]:
        return

    desc = MoonrakerNumberSensorDescription(
        key="speed_factor",
        sensor_name="gcode_move",
        name="Speed Factor",
        status_key="speed_factor",
        subscriptions=[("gcode_move", "speed_factor")],
        icon="mdi:speedometer",
        unit=PERCENTAGE,
        update_code="M220 S",
        max_value=200,
    )

    coordinator.load_sensor_data([desc])
    await coordinator.async_refresh()
    async_add_entities(
        [MoonrakerNumber(coordinator, entry, desc, value_multiplier=100.0)]
    )


async def async_setup_fan_speed(coordinator, entry, async_add_entities):
    """Set up fan speed number entity."""

    object_list = await coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)
    if "fan" not in object_list["objects"]:
        return

    desc = MoonrakerNumberSensorDescription(
        key="fan_speed",
        sensor_name="fan",
        name="Fan Speed",
        status_key="speed",
        subscriptions=[("fan", "speed")],
        icon="mdi:fan",
        unit=PERCENTAGE,
        update_code="M106 S",
        max_value=100,
    )

    coordinator.load_sensor_data([desc])
    await coordinator.async_refresh()
    async_add_entities(
        [MoonrakerFanSpeed(coordinator, entry, desc, value_multiplier=100.0)]
    )


_LOGGER = logging.getLogger(__name__)


def _coerce_float(value: Any) -> float | None:
    """Coerce arbitrary values to float."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MoonrakerPWMOutputPin(BaseMoonrakerEntity, NumberEntity):
    """Moonraker PWM output pin class."""

    def __init__(
        self,
        coordinator,
        entry,
        description,
    ) -> None:
        """Initialize the switch class."""
        super().__init__(coordinator, entry)
        self.pin = description.sensor_name.replace("output_pin ", "")
        self._attr_mode = NumberMode.SLIDER
        self.entity_description: MoonrakerNumberSensorDescription = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self._attr_icon = description.icon
        self.coordinator: MoonrakerDataUpdateCoordinator = coordinator
        self._attr_native_value = self._extract_native_value()

    async def async_set_native_value(self, value: float) -> None:
        """Set native Value."""
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"SET_PIN PIN={self.pin} VALUE={round(value / 100, 2)}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()

    def _extract_native_value(self) -> float:
        """Return the current PWM value as percentage."""
        status = self.coordinator.data.get("status", {})
        obj = status.get(self.sensor_name, {})
        raw_value = obj.get("value") if isinstance(obj, dict) else None
        coerced = _coerce_float(raw_value)
        return coerced * 100 if coerced is not None else 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self._extract_native_value()
        self.async_write_ha_state()


class MoonrakerNumber(BaseMoonrakerEntity, NumberEntity):
    """Generic Moonraker number class."""

    def __init__(
        self,
        coordinator,
        entry,
        description,
        value_multiplier: float = 1.0,
    ) -> None:
        """Initialize the number class."""
        super().__init__(coordinator, entry)
        self._attr_mode = NumberMode.SLIDER
        self.entity_description: MoonrakerNumberSensorDescription = description
        self.sensor_name = description.sensor_name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_has_entity_name = True
        self._attr_icon = description.icon
        self._attr_native_max_value = (
            float(description.max_value)
            if description.max_value is not None
            else None
        )
        self._attr_native_min_value = (
            float(description.min_value)
            if description.min_value is not None
            else 0.0
        )
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.unit
        self.update_string = description.update_code
        self.value_multiplier = value_multiplier
        self.coordinator: MoonrakerDataUpdateCoordinator = coordinator
        self._attr_native_value = self._extract_native_value()

    async def async_set_native_value(self, value: float) -> None:
        """Set native Value."""
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"{self.update_string}{value}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()

    def _extract_native_value(self) -> float:
        """Return the current number value, falling back to zero when missing."""
        status_key = self.entity_description.status_key
        if status_key is None:
            return 0.0
        status = self.coordinator.data.get("status", {})
        obj = status.get(self.sensor_name, {})
        raw_value = obj.get(status_key) if isinstance(obj, dict) else None
        coerced = _coerce_float(raw_value)
        return coerced * self.value_multiplier if coerced is not None else 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self._extract_native_value()
        self.async_write_ha_state()


class MoonrakerFanSpeed(MoonrakerNumber):
    """Moonraker fan speed number class."""

    async def async_set_native_value(self, value: float) -> None:
        """Set native Value."""
        # Apply the multiplier before sending to printer
        adjusted_value = 255 * (value / 100)
        await self.coordinator.async_send_data(
            METHODS.PRINTER_GCODE_SCRIPT,
            {"script": f"{self.update_string}{int(adjusted_value)}"},
        )
        self._attr_native_value = value
        self.async_write_ha_state()
