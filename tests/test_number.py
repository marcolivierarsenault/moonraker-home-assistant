"""Test moonraker number."""

from unittest.mock import patch

import pytest
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS

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
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    get_data["status"]["gcode_move"]["speed_factor"] = 1.5
    await hass.async_block_till_done()

    state = hass.states.get("number.mainsail_speed_factor")
    assert state.state == "150.0"


async def test_speed_factor_set_value(hass, get_data):
    """Test speed factor number entity set value."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "custom_components.moonraker.MoonrakerApiClient.async_send_data"
    ) as mock_send_data:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.mainsail_speed_factor", "value": 150},
            blocking=True,
        )
        mock_send_data.assert_called_once_with(
            "printer.gcode.script", {"script": "M220 S150"}
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
