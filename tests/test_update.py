"""Test Moonraker update entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.entity_platform import async_get_platforms
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advance_moonraker_control.const import DOMAIN, METHODS
from custom_components.advance_moonraker_control.update import async_setup_entry

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.start"),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
        patch(
            "custom_components.advance_moonraker_control._async_is_tcp_reachable",
            return_value=True,
        ),
    ):
        yield


def _find_entity(hass, unique_id):
    """Locate a moonraker entity by unique id across platforms."""
    for platform in async_get_platforms(hass, DOMAIN):
        for entity in platform.entities.values():
            if getattr(entity, "unique_id", None) == unique_id:
                return entity
    return None


async def test_update_entities_created(hass, get_default_api_response):
    """Update entities are created for each versioned component."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("update.mainsail_crownest_update")
    assert state is not None
    assert state.attributes["installed_version"] == "v4.0.4-6"
    assert state.attributes["latest_version"] == "v4.1.1-1"
    assert state.attributes["component"] == "crownest"

    # system component is skipped
    assert hass.states.get("update.mainsail_system_update") is None

    mainsail = hass.states.get("update.mainsail_mainsail_update")
    assert mainsail is not None
    assert mainsail.state == "off"  # versions match → no update


async def test_update_install_for_web_client(hass, get_default_api_response):
    """Installing a web client update calls the client upgrade method."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    calls = []

    async def capture(method, params=None):
        calls.append((method, params))

    coordinator.async_send_data = capture
    entity = _find_entity(hass, "test_update_mainsail")
    assert entity is not None
    await entity.async_install()
    assert calls
    assert calls[0][0] == METHODS.MACHINE_UPDATE_CLIENT_UPGRADE
    assert calls[0][1] == {"name": "mainsail"}


async def test_update_no_install_for_non_web(hass, get_default_api_response):
    """Non-web components do not expose an install feature."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    from homeassistant.components.update import UpdateEntityFeature

    entity = _find_entity(hass, "test_update_crownest")
    assert entity is not None
    assert not (entity.supported_features & UpdateEntityFeature.INSTALL)


async def test_update_setup_fetches_when_no_data(hass):
    """Setup falls back to fetching machine update status."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="fetch")
    coordinator = SimpleNamespace(
        data={},
        config_entry=entry,
        api_device_name="printer",
        async_fetch_data=AsyncMock(
            return_value={
                "version_info": {
                    "mainsail": {
                        "version": "v2.8.0",
                        "remote_version": "v2.9.0",
                        "client_type": "web",
                    },
                    "system": {"package_count": 3},
                    "junk": {},
                }
            }
        ),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert len(entities) == 1
    assert entities[0]._attr_latest_version == "v2.9.0"
    assert entities[0]._attr_installed_version == "v2.8.0"


async def test_update_setup_without_version_info(hass):
    """Missing or malformed version info creates no entities."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="no-info")
    coordinator = SimpleNamespace(
        data={},
        config_entry=entry,
        api_device_name="printer",
        async_fetch_data=AsyncMock(return_value={"error": "no updater"}),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert entities == []


async def test_update_coordinator_refresh(hass, get_default_api_response):
    """Entities refresh version attributes on coordinator updates."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entity = _find_entity(hass, "test_update_crownest")
    assert entity is not None
    coordinator.data["machine_update"]["version_info"]["crownest"]["remote_version"] = (
        "v9.9.9"
    )
    entity._handle_coordinator_update()
    assert entity._attr_latest_version == "v9.9.9"
