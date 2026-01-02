"""Test moonraker setup process."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta
from types import SimpleNamespace
from custom_components.moonraker.const import PRINTSTATES

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import (
    MoonrakerDataUpdateCoordinator,
    _build_thumbnail_path,
    _normalize_gcode_path,
    _strip_gcode_root,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG, MOCK_CONFIG_WITH_NAME


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


def test_normalize_gcode_path_empty():
    """Return empty parts for empty input."""
    assert _normalize_gcode_path("") == ("", None)
    assert _normalize_gcode_path(None) == ("", None)


def test_normalize_gcode_path_with_root_prefix():
    """Strip gcodes root from relative paths."""
    filename, root = _normalize_gcode_path("gcodes/subdir/file.gcode")
    assert filename == "subdir/file.gcode"
    assert root == "gcodes"


def test_normalize_gcode_path_with_absolute_path():
    """Extract gcodes root from absolute paths."""
    filename, root = _normalize_gcode_path(
        "/home/user/printer_data/gcodes/subdir/file.gcode"
    )
    assert filename == "subdir/file.gcode"
    assert root == "gcodes"


def test_strip_gcode_root_prefix():
    """Strip root prefix from thumbnail paths."""
    assert _strip_gcode_root("gcodes/.thumbs/file.png", "gcodes") == ".thumbs/file.png"


def test_strip_gcode_root_absolute():
    """Strip root prefix when embedded in an absolute path."""
    assert (
        _strip_gcode_root("/home/user/gcodes/.thumbs/file.png", "gcodes")
        == ".thumbs/file.png"
    )


def test_strip_gcode_root_without_root():
    """Leave paths untouched when no root is provided."""
    assert (
        _strip_gcode_root("subfolder/.thumbs/file.png", None)
        == "subfolder/.thumbs/file.png"
    )


def test_strip_gcode_root_without_root_prefix():
    """Strip gcodes prefix even without an explicit root."""
    assert _strip_gcode_root("gcodes/.thumbs/file.png", None) == ".thumbs/file.png"


def test_build_thumbnail_path_reuses_existing_dir():
    """Avoid duplicating directory segments."""
    assert (
        _build_thumbnail_path("subfolder", "subfolder/.thumbs/file.png", "gcodes")
        == "subfolder/.thumbs/file.png"
    )


def test_build_thumbnail_path_joins_dir():
    """Join the gcode directory when thumbnails are relative."""
    assert (
        _build_thumbnail_path("subfolder", ".thumbs/file.png", "gcodes")
        == "subfolder/.thumbs/file.png"
    )


def test_build_thumbnail_path_strips_dot_prefix():
    """Trim leading ./ for URL usage."""
    assert (
        _build_thumbnail_path("", "./.thumbs/file.png", "gcodes") == ".thumbs/file.png"
    )


async def test_setup_unload_and_reload_entry(hass):
    """Test entry setup and unload."""
    # Create a mock entry so we don't have to go through config flow

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(
        hass.data[DOMAIN][config_entry.entry_id], MoonrakerDataUpdateCoordinator
    )

    # Reload the entry and assert that the data from above is still there.
    hass.config_entries._entries[config_entry.entry_id] = config_entry
    assert await async_reload_entry(hass, config_entry) is None
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(
        hass.data[DOMAIN][config_entry.entry_id], MoonrakerDataUpdateCoordinator
    )

    # Unload the entry and verify that the data has been removed
    assert await async_unload_entry(hass, config_entry)
    assert config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_unload_and_reload_entry_with_name(hass):
    """Test entry setup with name and unload."""
    # Create a mock entry so we don't have to go through config flow

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG_WITH_NAME, entry_id="test"
    )
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(
        hass.data[DOMAIN][config_entry.entry_id], MoonrakerDataUpdateCoordinator
    )

    # Reload the entry and assert that the data from above is still there.
    hass.config_entries._entries[config_entry.entry_id] = config_entry
    assert await async_reload_entry(hass, config_entry) is None
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(
        hass.data[DOMAIN][config_entry.entry_id], MoonrakerDataUpdateCoordinator
    )

    # Unload the entry and verify that the data has been removed
    assert await async_unload_entry(hass, config_entry)
    assert config_entry.entry_id not in hass.data[DOMAIN]


async def test_async_send_data_exception(hass):
    """Test async_post_exception."""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=UpdateFailed,
        ),
        pytest.raises(UpdateFailed),
    ):
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        assert await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)

    assert await async_unload_entry(hass, config_entry)


async def test_setup_entry_exception(hass):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        side_effect=Exception,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            assert await async_setup_entry(hass, config_entry)


async def test_coordinator_passes_config_entry_to_super(hass):
    """Ensure the coordinator forwards the config entry to the base class."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="config")

    captured: dict[str, dict] = {}
    original_init = DataUpdateCoordinator.__init__

    def wrapped_init(self, hass_param, logger, *args, **kwargs):
        captured["kwargs"] = dict(kwargs)
        captured["args"] = (hass_param, logger, *args)
        return original_init(self, hass_param, logger, *args, **kwargs)

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__",
        new=wrapped_init,
    ):
        coordinator = MoonrakerDataUpdateCoordinator(
            hass,
            client=MagicMock(),
            config_entry=config_entry,
            api_device_name="printer",
        )

    assert captured["kwargs"]["config_entry"] is config_entry
    assert coordinator.config_entry is config_entry


def load_data(endpoint, *args, **kwargs):
    """Load data."""
    if endpoint == "printer.info":
        return {"hostname": "mainsail"}

    raise Exception


async def test_failed_first_refresh(hass):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        side_effect=load_data,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            assert await async_setup_entry(hass, config_entry)


async def test_set_custom_gcode_service(hass):
    """Test custom GCode Services."""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_id = list(hass.data["device_registry"].devices.keys())

    # Test that the function call works in its entirety.
    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_sensors:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": device_id,
                "gcode": "STATUS",
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        mock_sensors.assert_awaited_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="STATUS"
        )


async def test_send_gcode_list_payload_normalizes_script(hass):
    """Ensure list payloads join into a single script."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="list_payload"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = list(hass.data["device_registry"].devices.keys())
    target_device_id = device_ids[0]

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": target_device_id,
                "gcode": ["G28", "M105"],
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(
        METHODS.PRINTER_GCODE_SCRIPT.value, script="G28\nM105"
    )
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_empty_payload_skips_send(hass):
    """Ensure empty payloads do not call Moonraker."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="empty_payload"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = list(hass.data["device_registry"].devices.keys())

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": device_ids,
                "gcode": ["   ", ""],
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_accepts_config_entry_id_and_deduplicates(hass):
    """Ensure config entry IDs are accepted and deduplicated."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="entry_fallback"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = list(hass.data["device_registry"].devices.keys())
    primary_device_id = device_ids[0]

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [primary_device_id, config_entry.entry_id],
                "gcode": "G0",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(METHODS.PRINTER_GCODE_SCRIPT.value, script="G0")
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_identifier_fallback(hass):
    """Ensure identifiers populate entry IDs when config entries are missing."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="identifier_fallback"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    identifier_device_id = "identifier-device"
    identifier_device = SimpleNamespace(
        config_entries=set(),
        primary_config_entry=None,
        identifiers={(DOMAIN, config_entry.entry_id)},
    )

    def async_get_override(device_id):
        if device_id == identifier_device_id:
            return identifier_device
        return original_async_get(device_id)

    with patch.object(dev_reg, "async_get", side_effect=async_get_override), patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [identifier_device_id],
                "gcode": "M105",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(
        METHODS.PRINTER_GCODE_SCRIPT.value, script="M105"
    )
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_skips_device_without_entries(hass):
    """Skip devices that cannot be linked to config entries."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="orphan_device"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    orphan_device_id = "orphan-device"
    orphan_device = SimpleNamespace(
        config_entries=set(),
        primary_config_entry=None,
        identifiers=set(),
    )

    def async_get_override(device_id):
        if device_id == orphan_device_id:
            return orphan_device
        return original_async_get(device_id)

    with patch.object(dev_reg, "async_get", side_effect=async_get_override), patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [orphan_device_id],
                "gcode": "G90",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_skips_unloaded_entries(hass):
    """Skip devices whose entries are not currently loaded."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="missing_entry"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    missing_device_id = "missing-device"
    missing_device = SimpleNamespace(
        config_entries={"ghost-entry"},
        primary_config_entry=None,
        identifiers=set(),
    )

    def async_get_override(device_id):
        if device_id == missing_device_id:
            return missing_device
        return original_async_get(device_id)

    with patch.object(dev_reg, "async_get", side_effect=async_get_override), patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [missing_device_id],
                "gcode": "G91",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_unknown_device_is_ignored(hass):
    """Unknown device IDs should be ignored."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="unknown_device"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": "unknown-device",
                "gcode": "M115",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_call.await_count == 0
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.asyncio
async def test_polling_interval_changes_on_print_state(hass, get_data):
    """Test polling interval changes based on print state transitions."""
    from custom_components.moonraker.const import DOMAIN
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from .const import MOCK_CONFIG

    # Set initial state to standby
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value

    # Setup coordinator
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="test_polling"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Default should be 30 seconds
    assert coordinator.update_interval == timedelta(seconds=30)

    with patch.object(coordinator, "_schedule_refresh") as mock_refresh:
        # Simulate a state change to printing
        get_data["status"]["print_stats"]["state"] = PRINTSTATES.PRINTING.value
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=2)
        assert mock_refresh.called

        mock_refresh.reset_mock()

        # Simulate a state change back to standby
        get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=30)
        assert mock_refresh.called

        mock_refresh.reset_mock()

        # Simulate no state change (still standby)
        await coordinator._async_update_data()
        # Should not call _schedule_refresh again
        assert not mock_refresh.called


@pytest.mark.asyncio
async def test_polling_interval_no_change_on_same_state(hass, get_data):
    """Test polling interval does not change or reschedule if state is unchanged."""
    from custom_components.moonraker.const import DOMAIN
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from .const import MOCK_CONFIG

    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="test_polling2"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with patch.object(coordinator, "_schedule_refresh") as mock_refresh:
        # Call update with the same state
        await coordinator._async_update_data()
        assert not mock_refresh.called
        assert coordinator.update_interval == timedelta(seconds=30)
