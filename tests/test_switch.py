"""Switch Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_UNAVAILABLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from pytest_homeassistant.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS
from custom_components.moonraker.switch import async_setup_output_pin

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_output_pins_missing_config_are_skipped(hass):
    """Skip unknown and vendor-specific output pin objects without failing setup."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("number.mainsail_output_pin_missing_config") is None
    assert hass.states.get("switch.mainsail_output_pin_missing_config") is None
    assert hass.states.get("number.mainsail_smart_output_pin_polar_cooler") is None
    assert hass.states.get("switch.mainsail_smart_output_pin_polar_cooler") is None


async def test_switch_setup_skips_output_pin_without_config():
    """Skip a standard output pin when its config section is absent."""

    class FakeCoordinator:
        """Return an incomplete output-pin response."""

        def __init__(self):
            self.loaded = None
            self.refreshed = False

        async def async_fetch_data(self, method, params=None, quiet=False):
            if method == METHODS.PRINTER_OBJECTS_LIST:
                return {
                    "objects": [
                        "output_pin missing_config",
                        "smart_output_pin polar_cooler",
                    ]
                }
            if method == METHODS.PRINTER_OBJECTS_QUERY:
                return {"status": {"configfile": {"settings": {}}}}
            raise AssertionError(f"Unexpected method: {method}")

        def load_sensor_data(self, sensors):
            self.loaded = sensors

        async def async_get_config_settings(self):
            return await self.async_fetch_data(METHODS.PRINTER_OBJECTS_QUERY)

        async def async_get_printer_objects_list(self):
            return await self.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)

        async def async_refresh_new_data(self):
            self.refreshed = True

    coordinator = FakeCoordinator()
    added_entities = []

    await async_setup_output_pin(coordinator, object(), added_entities.extend)

    assert coordinator.loaded == []
    assert coordinator.refreshed
    assert added_entities == []


# test switches
@pytest.mark.parametrize(
    "switch, switch_type",
    [
        ("mainsail_light", "power"),
        ("mainsail_printer", "power"),
        ("mainsail_output_pin_digital", "pin"),
    ],
)
async def test_switch_turn_on(hass, switch, switch_type, get_default_api_response):
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
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: f"switch.{switch}",
            },
            blocking=True,
        )

        if switch_type == "power":
            mock_api.assert_any_call(
                METHODS.MACHINE_DEVICE_POWER_POST_DEVICE.value,
                device=switch.split("_")[1],
                action="on",
            )
        elif switch_type == "pin":
            mock_api.assert_any_call(
                METHODS.PRINTER_GCODE_SCRIPT.value,
                script=f"SET_PIN PIN={switch.split('_')[3]} VALUE=1",
            )


# test switches
@pytest.mark.parametrize(
    "switch, switch_type",
    [
        ("mainsail_light", "power"),
        ("mainsail_printer", "power"),
        ("mainsail_output_pin_digital", "pin"),
    ],
)
async def test_switch_turn_off(hass, switch, switch_type, get_default_api_response):
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
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {
                ATTR_ENTITY_ID: f"switch.{switch}",
            },
            blocking=True,
        )

        if switch_type == "power":
            mock_api.assert_any_call(
                METHODS.MACHINE_DEVICE_POWER_POST_DEVICE.value,
                device=switch.split("_")[1],
                action="off",
            )
        elif switch_type == "pin":
            mock_api.assert_any_call(
                METHODS.PRINTER_GCODE_SCRIPT.value,
                script=f"SET_PIN PIN={switch.split('_')[3]} VALUE=0",
            )


async def test_power_devices_missing_key(hass, get_default_api_response):
    """Missing 'devices' key (e.g. Moonraker offline) must not crash setup."""
    response_without_devices = {**get_default_api_response}
    response_without_devices.pop("devices", None)

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value=response_without_devices,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state.value == "loaded"
    assert hass.states.get("switch.mainsail_printer") is None


async def test_power_device_missing_from_coordinator_data(hass, get_power_devices):
    """Power state going missing after setup marks the switch unavailable, not crashed."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("switch.mainsail_printer")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE

    get_power_devices["devices"] = []
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={"devices": []},
    ):
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("switch.mainsail_printer")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_output_pin_config_missing_skips_entity(hass, get_data):
    """An output pin with unknown config must be skipped, not guessed as digital."""
    get_data["status"]["configfile"]["settings"].pop("output_pin digital", None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("switch.mainsail_output_pin_digital") is None


async def test_output_pin_unavailable_while_value_missing(hass, get_data):
    """A digital output pin is unavailable while its value is missing."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entity_id = "switch.mainsail_output_pin_digital"

    saved = get_data["status"].pop("output_pin digital")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    get_data["status"]["output_pin digital"] = saved
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"


async def test_power_device_missing_status(hass, get_power_devices):
    """A power device without a status is unavailable."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    get_power_devices["devices"][0].pop("status")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("switch.mainsail_printer").state == STATE_UNAVAILABLE
