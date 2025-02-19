"""Light Tests."""

from unittest.mock import patch

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.light import SERVICE_TURN_ON, SERVICE_TURN_OFF
from homeassistant.const import ATTR_ENTITY_ID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


# test light on
@pytest.mark.parametrize(
    "light",
    [("mainsail_led_chamber"), ("mainsail_neopixel_CAMERA")],
)
async def test_light_turn_on(hass, light, get_default_api_response):
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
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: f"light.{light}",
                "brightness": 255,
            },
            blocking=True,
        )

        mock_api.assert_any_call(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script=f"SET_LED LED=\"{light.split('_')[2]}\" RED=1.0 GREEN=1.0 BLUE=1.0 WHITE=1.0 SYNC=0 TRANSMIT=1",
        )


# test light on default brightness
@pytest.mark.parametrize(
    "light",
    [("mainsail_led_chamber")],
)
async def test_light_turn_on_default(hass, light, get_default_api_response):
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
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: f"light.{light}",
            },
            blocking=True,
        )

        mock_api.assert_any_call(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script=f"SET_LED LED=\"{light.split('_')[2]}\" RED=1.0 GREEN=1.0 BLUE=1.0 WHITE=1.0 SYNC=0 TRANSMIT=1",
        )


# test light on rgb
@pytest.mark.parametrize(
    "light",
    [("mainsail_dotstar_strip")],
)
async def test_light_turn_on_rgb(hass, light, get_default_api_response):
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
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: f"light.{light}",
                "rgb_color": (255, 0, 127),
            },
            blocking=True,
        )

        mock_api.assert_any_call(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script=f"SET_LED LED=\"{light.split('_')[2]}\" RED=1.0 GREEN=0.0 BLUE=0.5 WHITE=0.0 SYNC=0 TRANSMIT=1",
        )


# test light off
@pytest.mark.parametrize(
    "light",
    [("mainsail_led_chamber")],
)
async def test_light_turn_off(hass, light, get_default_api_response):
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
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {
                ATTR_ENTITY_ID: f"light.{light}",
            },
            blocking=True,
        )

        mock_api.assert_any_call(
            METHODS.PRINTER_GCODE_SCRIPT.value,
            script=f"SET_LED LED=\"{light.split('_')[2]}\" RED=0.0 GREEN=0.0 BLUE=0.0 WHITE=0.0 SYNC=0 TRANSMIT=1",
        )
