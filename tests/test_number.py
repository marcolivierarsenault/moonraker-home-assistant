"""Test moonraker number."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number.const import SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS, OBJ
from custom_components.moonraker.number import (
    MoonrakerNumber,
    MoonrakerNumberSensorDescription,
    _coerce_float,
    async_setup_temperature_target,
)
from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_targets(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("number.mainsail_bed_target").state == "60.0"
    assert hass.states.get("number.mainsail_extruder_target").state == "205.0"
    assert hass.states.get("number.mainsail_extruder1_target").state == "220.0"
    fan_target = hass.states.get("number.mainsail_fan_temp_target")
    assert fan_target.state == "35.0"
    assert fan_target.attributes["max"] == 70.0
    assert fan_target.attributes["min"] == 10.0
    chamber_target = hass.states.get("number.mainsail_my_super_heater_target")
    assert chamber_target.state == "32.0"
    assert chamber_target.attributes["max"] == 90.0
    assert chamber_target.attributes["min"] == 25.0
    assert chamber_target.attributes["icon"] == "mdi:radiator"
    mixed_target = hass.states.get("number.mainsail_mixed_case_target")
    assert mixed_target.state == "35.0"
    assert mixed_target.attributes["max"] == 85.0
    assert mixed_target.attributes["min"] == 30.0


# test number
@pytest.mark.parametrize(
    "number",
    [("mainsail_output_pin_pwm"), ("mainsail_output_pin_CAPITALIZED")],
)
async def test_number_set_value(hass, number, get_default_api_response):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: f"number.{number}",
                "value": 50,
            },
            blocking=True,
        )

        mock_api.assert_any_call(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script=f"SET_PIN PIN={number.split('_')[3]} VALUE=0.5",
        )


async def test_set_target(hass, get_default_api_response):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_extruder_target",
                "value": 50,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script="M104 T0 S50.0",
        )

        mock_api.reset_mock()
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_extruder1_target",
                "value": 60,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script="M104 T1 S60.0",
        )

        mock_api.reset_mock()
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_bed_target",
                "value": 70,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script="M140 S70.0",
        )

        mock_api.reset_mock()
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_fan_temp_target",
                "value": 45,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script="SET_TEMPERATURE_FAN_TARGET FAN=fan_temp TARGET=45.0",
        )

        mock_api.reset_mock()
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_my_super_heater_target",
                "value": 45,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script="SET_HEATER_TEMPERATURE HEATER=my_super_heater TARGET=45.0",
        )

        mock_api.reset_mock()
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_mixed_case_target",
                "value": 55,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script="SET_HEATER_TEMPERATURE HEATER=MIXED_CASE TARGET=55.0",
        )


async def test_speed_factor(hass, get_data):
    """Test speed factor number entity."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_speed_factor")
    assert state.state == "200.0"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["icon"] == "mdi:speedometer"
    assert state.attributes["mode"] == "slider"
    assert state.attributes["max"] == 200.0


async def test_speed_factor_update(hass, get_data):
    """Test speed factor number entity update."""
    get_data["status"]["gcode_move"]["speed_factor"] = 1.5
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # get_data["status"]["gcode_move"]["speed_factor"] = 1.5
    # await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_speed_factor")
    assert state.state == "150.0"


async def test_speed_factor_set_value(hass, get_default_api_response):
    """Test speed factor number entity set value."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_speed_factor",
                "value": 150,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="M220 S150.0"
        )


async def test_speed_factor_missing(hass, get_data, get_printer_objects_list):
    """Test speed factor number entity when gcode_move is missing."""
    get_printer_objects_list["objects"].remove("gcode_move")
    get_data["status"].pop("gcode_move", None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_speed_factor")
    assert state is None


async def test_fan_speed(hass, get_data):
    """Test fan speed number entity."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_fan_speed")
    assert state.state == "51.23"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["icon"] == "mdi:fan"
    assert state.attributes["mode"] == "slider"
    assert state.attributes["max"] == 100.0


async def test_fan_speed_update(hass, get_data):
    """Test fan speed number entity update."""
    get_data["status"]["fan"]["speed"] = 0.75
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_fan_speed")
    assert state.state == "75.0"


async def test_fan_speed_set_value(hass, get_default_api_response):
    """Test fan speed number entity set value."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.mainsail_fan_speed",
                "value": 50,
            },
            blocking=True,
        )

        await hass.async_block_till_done()
        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="M106 S127"
        )


@pytest.mark.parametrize(
    ("obj", "fan_name"),
    [
        ("fan_generic cooling_fan", "cooling_fan"),
    ],
)
async def test_fan_generic_speed_entity_created(
    hass, get_data, get_printer_objects_list, obj, fan_name
):
    """fan_generic objects should create controllable Number entities."""
    # Ensure classic [fan] is NOT present.
    if "fan" in get_printer_objects_list["objects"]:
        get_printer_objects_list["objects"].remove("fan")
    get_data["status"].pop("fan", None)

    if obj not in get_printer_objects_list["objects"]:
        get_printer_objects_list["objects"].append(obj)
    get_data["status"][obj] = {"speed": 0.5123}

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Resolve entity_id via entity registry (don’t hardcode).
    entity_registry = er.async_get(hass)
    number_entries = {
        entry.unique_id: entry.entity_id
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN and entry.domain == NUMBER_DOMAIN
    }
    unique_id = f"{config_entry.entry_id}_fan_generic_{fan_name}_speed"
    entity_id = number_entries[unique_id]

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "51.23"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["icon"] == "mdi:fan"


@pytest.mark.parametrize(
    ("obj", "fan_name", "value", "expected_speed"),
    [
        ("fan_generic cooling_fan", "cooling_fan", 50, "0.5"),
    ],
)
async def test_fan_generic_speed_set_value(
    hass,
    get_default_api_response,
    get_data,
    get_printer_objects_list,
    obj,
    fan_name,
    value,
    expected_speed,
):
    """fan_generic Number should send SET_FAN_SPEED with SPEED scaled 0..1."""
    # Ensure classic [fan] is NOT present.
    if "fan" in get_printer_objects_list["objects"]:
        get_printer_objects_list["objects"].remove("fan")
    get_data["status"].pop("fan", None)

    if obj not in get_printer_objects_list["objects"]:
        get_printer_objects_list["objects"].append(obj)
    get_data["status"][obj] = {"speed": 0.2}

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    number_entries = {
        entry.unique_id: entry.entity_id
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN and entry.domain == NUMBER_DOMAIN
    }
    unique_id = f"{config_entry.entry_id}_fan_generic_{fan_name}_speed"
    entity_id = number_entries[unique_id]

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ) as mock_api:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, "value": value},
            blocking=True,
        )
        await hass.async_block_till_done()

        mock_api.assert_called_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script=f"SET_FAN_SPEED FAN={fan_name} SPEED={expected_speed}",
        )


async def test_fan_speed_no_supported_fans(hass, get_data, get_printer_objects_list):
    """Exit early when no controllable fan objects are present."""

    def _objects_list(payload: dict) -> list:
        if "objects" in payload:
            return payload["objects"]
        return payload["result"]["objects"]

    objects = _objects_list(get_printer_objects_list)

    # Remove all objects that could create fan speed number entities
    objects[:] = [
        obj
        for obj in objects
        if obj != "fan"
        and not obj.startswith("fan_generic ")
        and not obj.startswith("fan ")
    ]

    # Also remove their status blocks if present
    status = get_data.get("status", {})
    for key in list(status.keys()):
        if key == "fan" or key.startswith("fan_generic ") or key.startswith("fan "):
            status.pop(key, None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Only assert fan *speed* numbers are absent (temperature_fan targets may still exist)
    ent_reg = er.async_get(hass)
    fan_speed_numbers = [
        entity_id
        for entity_id in ent_reg.entities
        if entity_id.startswith("number.mainsail_") and "fan_speed" in entity_id
    ]
    assert fan_speed_numbers == []


async def test_temperature_targets_handle_none(hass, get_data):
    """Ensure number entities handle None target values gracefully."""
    get_data["status"]["heater_bed"]["target"] = None
    get_data["status"]["extruder"]["target"] = None

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    bed_state = hass.states.get("number.mainsail_bed_target")
    assert bed_state.state == "0.0"
    extruder_state = hass.states.get("number.mainsail_extruder_target")
    assert extruder_state.state == "0.0"


async def test_fan_speed_missing(hass, get_data, get_printer_objects_list):
    """Test fan speed number entity when fan is missing."""
    get_printer_objects_list["objects"].remove("fan")
    get_data["status"].pop("fan", None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_fan_speed")
    assert state is None


async def test_temperature_fan_config_fallbacks(hass):
    """Ensure temperature fan entities cover config fallbacks."""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert "temperature_fan missing_config" in coordinator.data["status"]
    assert "temperature_fan missing_config" in coordinator.query_obj[OBJ]

    entity_registry = er.async_get(hass)

    number_entries = {
        entry.unique_id: entry.entity_id
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN and entry.domain == NUMBER_DOMAIN
    }
    available_ids = sorted(number_entries)
    expected_missing_unique_id = (
        f"{config_entry.entry_id}_temperature_fan_missing_config_target_control"
    )
    assert expected_missing_unique_id in number_entries
    missing_entity_id = number_entries[expected_missing_unique_id]
    missing_state = hass.states.get(missing_entity_id)
    assert missing_state is not None
    assert missing_state.attributes["min"] == 0.0
    assert missing_state.attributes["max"] == 100.0

    uppercase_unique_id = (
        f"{config_entry.entry_id}_temperature_fan_FAN_CASE_target_control"
    )
    uppercase_entity_id = number_entries.get(uppercase_unique_id)
    assert uppercase_entity_id is not None, available_ids
    uppercase_state = hass.states.get(uppercase_entity_id)
    assert uppercase_state.attributes["min"] == 5.0
    assert uppercase_state.attributes["max"] == 65.0


async def test_heater_generic_number_config_fallbacks(hass):
    """Ensure heater_generic numbers handle config fallbacks."""

    class FakeCoordinator:
        """Minimal coordinator stub for testing."""

        def __init__(self, hass_instance):
            self.hass = hass_instance
            self.api_device_name = "Mainsail"
            self.data = {
                "status": {
                    "heater_generic MIXED_CASE": {
                        "target": 35.0,
                        "temperature": 33.0,
                        "power": 0.4,
                    },
                    "heater_generic orphan_heater": {
                        "target": 40.0,
                        "temperature": 30.0,
                        "power": 0.1,
                    },
                }
            }
            self.loaded = []
            self.query_obj = {}
            self._listeners = []

        async def async_fetch_data(self, method, params=None, quiet=False):
            if method == METHODS.PRINTER_OBJECTS_QUERY:
                return {
                    "status": {
                        "configfile": {
                            "settings": {
                                "heater_generic mixed_case": {
                                    "max_temp": 85.0,
                                    "min_temp": 30.0,
                                }
                            }
                        }
                    }
                }
            if method == METHODS.PRINTER_OBJECTS_LIST:
                return {
                    "objects": [
                        "heater_generic MIXED_CASE",
                        "heater_generic orphan_heater",
                    ]
                }
            raise AssertionError(f"Unexpected method: {method}")

        def add_query_objects(self, obj, field):
            self.query_obj.setdefault(obj, set()).add(field)

        def load_sensor_data(self, sensors):
            self.loaded.extend(sensors)

        async def async_refresh(self):
            return

        def async_add_listener(self, update_callback):
            self._listeners.append(update_callback)
            return lambda: None

    coordinator = FakeCoordinator(hass)
    entry = SimpleNamespace(entry_id="test")
    added_entities = []

    def capture_entities(entities):
        added_entities.extend(entities)

    await async_setup_temperature_target(coordinator, entry, capture_entities)

    assert len(coordinator.loaded) == 2
    assert len(added_entities) == 2
    added_by_name = {
        entity.entity_description.name: entity for entity in added_entities
    }

    mixed_entity = added_by_name["Mixed Case Target"]
    assert mixed_entity.native_value == 35.0
    assert mixed_entity.native_max_value == 85.0
    assert mixed_entity.native_min_value == 30.0
    assert (
        mixed_entity.update_string == "SET_HEATER_TEMPERATURE HEATER=MIXED_CASE TARGET="
    )

    orphan_entity = added_by_name["Orphan Heater Target"]
    assert orphan_entity.native_value == 40.0
    assert orphan_entity.native_max_value is None
    assert orphan_entity.native_min_value == 0.0
    assert (
        orphan_entity.update_string
        == "SET_HEATER_TEMPERATURE HEATER=orphan_heater TARGET="
    )
    assert coordinator.query_obj["heater_generic MIXED_CASE"] == {"target"}
    assert coordinator.query_obj["heater_generic orphan_heater"] == {"target"}


def test_coerce_float_handles_invalid_input():
    """_coerce_float should return None on invalid values."""
    assert _coerce_float("not-a-number") is None
    assert _coerce_float({"value": 1}) is None


async def test_number_with_no_status_key_defaults_to_zero(hass):
    """MoonrakerNumber falls back to zero when no status key is defined."""

    class DummyCoordinator:
        """Minimal coordinator for stateless number testing."""

        def __init__(self):
            self.api_device_name = "Mainsail"
            self.data = {"status": {}}
            self._listeners = []

        async def async_send_data(self, *_args, **_kwargs):
            return None

        def async_add_listener(self, update_callback):
            self._listeners.append(update_callback)
            return lambda: None

    coordinator = DummyCoordinator()
    entry = SimpleNamespace(entry_id="noop")
    desc = MoonrakerNumberSensorDescription(
        key="stateless_control",
        sensor_name="gcode_move",
        name="Stateless Control",
        status_key=None,
        update_code="M220 S",
    )

    number = MoonrakerNumber(coordinator, entry, desc)
    assert number.native_value == 0.0

    # Even if coordinator data gains values, the missing status key keeps the value at zero
    coordinator.data["status"]["gcode_move"] = {"speed_factor": 1.5}
    assert number._extract_native_value() == 0.0
