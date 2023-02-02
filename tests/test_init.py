"""Test moonraker setup process."""
from unittest.mock import patch
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.exceptions import ConfigEntryNotReady
from custom_components.moonraker import (
    MoonrakerDataUpdateCoordinator,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_setup_unload_and_reload_entry(hass, get_data, get_printer_info):
    """Test entry setup and unload."""
    # Create a mock entry so we don't have to go through config flow
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")

        assert await async_setup_entry(hass, config_entry)
        assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
        assert (
            type(hass.data[DOMAIN][config_entry.entry_id])
            == MoonrakerDataUpdateCoordinator
        )

        # Reload the entry and assert that the data from above is still there
        assert await async_reload_entry(hass, config_entry) is None
        assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
        assert (
            type(hass.data[DOMAIN][config_entry.entry_id])
            == MoonrakerDataUpdateCoordinator
        )

        # Unload the entry and verify that the data has been removed
        assert await async_unload_entry(hass, config_entry)
        assert config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_entry_exception(hass):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        side_effect=Exception,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")

        with pytest.raises(ConfigEntryNotReady):
            assert await async_setup_entry(hass, config_entry)


def load_data(endpoint, *args, **kwargs):
    if endpoint == "printer.info":
        return {"hostname": "mainsail"}
    else:
        raise Exception


async def test_failed_first_refresh(hass):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        side_effect=load_data,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")

        with pytest.raises(ConfigEntryNotReady):
            assert await async_setup_entry(hass, config_entry)
