"""Test moonraker number."""

from unittest.mock import patch

import pytest
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number.const import SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS, OBJ
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

    # Ensure the fallback entity remains registered for completeness
