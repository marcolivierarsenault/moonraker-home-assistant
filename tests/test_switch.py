"""Switch Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS
from custom_components.moonraker.switch import async_setup_output_pin

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch("custom_components.moonraker.MoonrakerApiClient.stop"),
    ):
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

        async def async_refresh(self):
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
