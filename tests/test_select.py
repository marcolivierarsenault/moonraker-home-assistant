"""Select Tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.select.const import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch("custom_components.moonraker.MoonrakerApiClient.stop"),
    ):
        yield


async def test_file_select(hass):
    """The file select should list stored files and keep the selection."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    coordinator.data = {
        **(coordinator.data or {}),
        "file_list": {"files": [{"path": "b.gcode"}, {"path": "a.gcode"}]},
    }
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get("select.mainsail_print_file")
    assert state is not None
    assert state.attributes["options"] == ["a.gcode", "b.gcode"]

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: "select.mainsail_print_file", ATTR_OPTION: "a.gcode"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert coordinator.selected_file == "a.gcode"


async def test_files_updater_normalizes_responses(hass):
    """The file-list updater normalizes list, dict, and malformed replies."""
    from custom_components.moonraker.select import _files_updater

    coordinator = SimpleNamespace(
        async_fetch_data=AsyncMock(return_value=[{"path": "a.gcode"}])
    )
    assert await _files_updater(coordinator) == {
        "file_list": {"files": [{"path": "a.gcode"}]}
    }

    coordinator.async_fetch_data = AsyncMock(return_value={"files": []})
    assert await _files_updater(coordinator) == {"file_list": {"files": []}}

    coordinator.async_fetch_data = AsyncMock(return_value="broken")
    assert await _files_updater(coordinator) == {"file_list": {"files": []}}


async def test_select_option_ignores_unknown_choice(hass):
    """Selecting a file not in the list is a no-op."""
    from custom_components.moonraker.select import MoonrakerFileSelect

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="x")
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        api_device_name="p",
        data={"file_list": {"files": [{"path": "a.gcode"}]}},
        selected_file=None,
        last_update_success=True,
    )
    entity = MoonrakerFileSelect(coordinator, config_entry)
    entity.async_write_ha_state = MagicMock()

    await entity.async_select_option("not-listed.gcode")
    assert coordinator.selected_file is None
    entity.async_write_ha_state.assert_not_called()
