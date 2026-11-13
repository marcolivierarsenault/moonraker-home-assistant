"""Test moonraker setup process."""

import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from custom_components.moonraker.const import PRINTSTATES

import voluptuous as vol

from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from pytest_homeassistant.common import MockConfigEntry

from custom_components.moonraker import (
    MoonrakerDataUpdateCoordinator,
    _async_is_tcp_reachable,
    _build_thumbnail_path,
    _merge_query,
    _moonraker_error_message,
    _normalize_gcode_path,
    _normalize_moonraker_port,
    _query_difference,
    _strip_gcode_root,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.moonraker.const import (
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    METHODS,
    OBJ,
)

from .const import MOCK_CONFIG, MOCK_CONFIG_WITH_NAME


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


def test_normalize_moonraker_port_uses_default_for_empty_values():
    """Empty configured ports should use the Moonraker default port."""
    assert _normalize_moonraker_port("") == DEFAULT_PORT
    assert _normalize_moonraker_port(None) == DEFAULT_PORT


def test_normalize_moonraker_port_converts_configured_values():
    """Configured ports should be converted to integers for socket probing."""
    assert _normalize_moonraker_port("7611") == 7611
    assert _normalize_moonraker_port(7611) == 7611


def test_normalize_gcode_path_empty():
    """Return empty parts for empty input."""
    assert _normalize_gcode_path("") == ("", None)
    assert _normalize_gcode_path(None) == ("", None)


def test_normalize_gcode_path_whitespace():
    """Return empty parts for whitespace-only input."""
    assert _normalize_gcode_path("   ") == ("", None)


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


def test_strip_gcode_root_none_path():
    """Return empty string when path is None."""
    assert _strip_gcode_root(None, "gcodes") == ""


def test_strip_gcode_root_whitespace_path():
    """Return empty string when path is whitespace."""
    assert _strip_gcode_root("   ", "gcodes") == ""


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


def test_build_thumbnail_path_missing_thumbnail():
    """Return None when thumbnail path is missing."""
    assert _build_thumbnail_path("subfolder", None, "gcodes") is None


def test_build_thumbnail_path_only_dot_prefix():
    """Return None when thumbnail path is only './'."""
    assert _build_thumbnail_path("subfolder", "./", "gcodes") is None


def test_build_thumbnail_path_joins_dir():
    """Join the gcode directory when thumbnails are relative."""
    assert (
        _build_thumbnail_path("subfolder", ".thumbs/file.png", "gcodes")
        == "subfolder/.thumbs/file.png"
    )


def test_build_thumbnail_path_empty_dir_after_strip():
    """Return thumbnail path when directory collapses to empty."""
    assert (
        _build_thumbnail_path("/", ".thumbs/file.png", "gcodes") == ".thumbs/file.png"
    )


def test_build_thumbnail_path_strips_dot_prefix():
    """Trim leading ./ for URL usage."""
    assert (
        _build_thumbnail_path("", "./.thumbs/file.png", "gcodes") == ".thumbs/file.png"
    )


async def test_tcp_reachable_success_closes_writer():
    """A successful TCP probe returns True and closes the connection."""
    writer = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch(
        "asyncio.open_connection",
        new_callable=AsyncMock,
        return_value=(MagicMock(), writer),
    ):
        assert await _async_is_tcp_reachable("1.2.3.4", DEFAULT_PORT)

    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_tcp_reachable_suppresses_close_errors():
    """Errors while closing the probe connection are ignored."""
    writer = MagicMock()
    writer.wait_closed = AsyncMock(side_effect=OSError)

    with patch(
        "asyncio.open_connection",
        new_callable=AsyncMock,
        return_value=(MagicMock(), writer),
    ):
        assert await _async_is_tcp_reachable("1.2.3.4", DEFAULT_PORT)

    writer.close.assert_called_once()


async def test_tcp_unreachable_returns_false():
    """A refused TCP probe returns False."""
    with patch(
        "asyncio.open_connection",
        new_callable=AsyncMock,
        side_effect=OSError,
    ):
        assert not await _async_is_tcp_reachable("1.2.3.4", DEFAULT_PORT)


async def test_gcode_detail_skips_empty_normalized_filename(hass):
    """Return defaults when normalized filename is empty."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    result = await coordinator._async_get_gcode_file_detail("/")

    assert result["thumbnails_path"] is None
    assert result["layer_count"] is None


async def test_gcode_detail_missing_thumbnails_skips_warning(hass, caplog):
    """Missing thumbnail metadata should not emit warnings."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    gcode_data = {
        "estimated_time": 10,
        "object_height": 5.5,
        "filament_total": 1.2,
        "layer_count": 20,
        "layer_height": 0.2,
        "first_layer_height": 0.3,
        "gcode_start_byte": 100,
        "gcode_end_byte": 200,
    }
    coordinator._async_fetch_data = AsyncMock(return_value=gcode_data)

    with caplog.at_level(logging.WARNING):
        result = await coordinator._async_get_gcode_file_detail("example.gcode")

    coordinator._async_fetch_data.assert_awaited_once_with(
        METHODS.SERVER_FILES_METADATA, {"filename": "example.gcode"}
    )
    assert result["thumbnails_path"] is None
    assert result["estimated_time"] == 10
    assert result["object_height"] == 5.5
    assert result["filament_total"] == 1.2
    assert result["layer_count"] == 20
    assert result["layer_height"] == 0.2
    assert result["first_layer_height"] == 0.3
    assert result["gcode_start_byte"] == 100
    assert result["gcode_end_byte"] == 200
    assert "failed to get thumbnails" not in caplog.text


async def test_gcode_detail_thumbnail_selection_ignores_invalid_entries(hass):
    """Pick the best thumbnail while ignoring invalid entries."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    gcode_data = {
        "thumbnails": [
            "not-a-dict",
            {"size": 12},
            {"relative_path": ".thumbs/fallback.png", "size": "bad"},
            {"relative_path": ".thumbs/best.png", "size": 999},
        ]
    }
    coordinator._async_fetch_data = AsyncMock(return_value=gcode_data)

    result = await coordinator._async_get_gcode_file_detail("subdir/file.gcode")

    coordinator._async_fetch_data.assert_awaited_once_with(
        METHODS.SERVER_FILES_METADATA, {"filename": "subdir/file.gcode"}
    )
    assert result["thumbnails_path"] == "subdir/.thumbs/best.png"


async def test_gcode_detail_thumbnail_selection_missing_paths(hass):
    """Return without thumbnail when no valid paths are provided."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    gcode_data = {"thumbnails": ["not-a-dict", {"size": 12}, {"relative_path": ""}]}
    coordinator._async_fetch_data = AsyncMock(return_value=gcode_data)

    result = await coordinator._async_get_gcode_file_detail("file.gcode")

    coordinator._async_fetch_data.assert_awaited_once_with(
        METHODS.SERVER_FILES_METADATA, {"filename": "file.gcode"}
    )
    assert result["thumbnails_path"] is None


async def test_add_query_objects_ignores_keys_after_full_object(hass):
    """Skip adding keys when object is already set to fetch all fields."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    coordinator.add_query_objects("gcode_macro TEST", None)
    assert coordinator.query_obj[OBJ]["gcode_macro TEST"] is None

    coordinator.add_query_objects("gcode_macro TEST", "variable_1")
    assert coordinator.query_obj[OBJ]["gcode_macro TEST"] is None


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


@pytest.mark.parametrize(
    ("printer_info", "expected_name"),
    [
        (
            {
                "device_type": "Anycubic Kobra 2 Pro",
                "state": "ready",
                "state_message": "Printer is ready",
                "software_version": "",
            },
            "Anycubic Kobra 2 Pro",
        ),
        (
            {
                "state": "ready",
                "state_message": "Printer is ready",
                "software_version": "",
            },
            MOCK_CONFIG["url"],
        ),
    ],
)
async def test_setup_entry_without_hostname_uses_fallback_name(
    hass, get_default_api_response, printer_info, expected_name
):
    """Use compatible names when printer.info does not include a hostname."""

    async def load_data(endpoint, *args, **kwargs):
        if endpoint == METHODS.PRINTER_INFO.value:
            return printer_info

        return get_default_api_response

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        entry_id=f"missing_hostname_{expected_name}",
    )
    config_entry.add_to_hass(hass)

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        side_effect=load_data,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert config_entry.title == expected_name
    assert coordinator.api_device_name == expected_name
    assert await async_unload_entry(hass, config_entry)


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


async def test_setup_entry_generic_exception_stays_warning_when_option_enabled(
    hass, caplog
):
    """Quiet unreachable mode must not hide non-reachability setup failures."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="setup_error_quiet",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=Exception,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert any(
        record.levelno == logging.WARNING
        and record.message == "Cannot configure moonraker instance"
        for record in caplog.records
    )


async def test_setup_entry_unreachable_logs_warning_by_default(hass, caplog):
    """Unreachable printers keep warning-level visibility unless silenced."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="offline")
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert "Cannot configure moonraker instance" in caplog.text
    assert any(
        record.levelno == logging.WARNING
        and "Cannot configure moonraker instance" in record.message
        for record in caplog.records
    )


async def test_setup_entry_empty_port_uses_default_for_reachability_probe(hass):
    """Empty stored ports remain accepted and are probed as the default port."""
    config = {**MOCK_CONFIG, CONF_PORT: ""}
    config_entry = MockConfigEntry(domain=DOMAIN, data=config, entry_id="empty_port")
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ) as is_reachable,
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    is_reachable.assert_awaited_once_with("1.2.3.4", DEFAULT_PORT)


async def test_setup_entry_unreachable_logs_debug_when_option_enabled(hass, caplog):
    """Unreachable printers can be configured to avoid warning-level log spam."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="offline_quiet",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert "Cannot configure moonraker instance" in caplog.text
    assert any(
        record.levelno == logging.DEBUG
        and "Cannot configure moonraker instance" in record.message
        for record in caplog.records
    )
    assert not any(
        record.levelno >= logging.WARNING
        and "Cannot configure moonraker instance" in record.message
        for record in caplog.records
    )


async def test_offline_poll_error_log_suppressed_when_option_enabled(hass, caplog):
    """The coordinator's failed-refresh error log honors quiet mode."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_offline_poll",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert coordinator.last_update_success

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
    ):
        await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not any(
        record.levelno >= logging.WARNING
        and "Error fetching moonraker data" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        record.levelno == logging.DEBUG and "is unreachable" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


async def test_offline_poll_fully_quiet_when_debug_disabled(hass, caplog):
    """Without debug logging enabled, quiet mode emits no record at all."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_offline_no_debug",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.INFO),
    ):
        await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not any(
        "Error fetching moonraker data" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


async def test_quiet_mode_rechecks_reachability_when_call_fails(hass, caplog):
    """A printer that drops while the websocket looks connected stays quiet."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_stale_connection",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    caplog.clear()

    with (
        patch.object(
            type(coordinator.moonraker.client),
            "is_connected",
            new_callable=PropertyMock,
            return_value=True,
        ),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
    ):
        await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert "is unreachable" in str(coordinator.last_exception)
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)

    assert await async_unload_entry(hass, config_entry)


async def test_quiet_mode_logs_other_failures_only_once(hass, caplog):
    """Quiet mode logs a non-reachability failure only on the first refresh."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_other_failure_once",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ),
        caplog.at_level(logging.DEBUG),
    ):
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    errors = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR
        and "Error fetching moonraker data" in record.getMessage()
    ]
    assert len(errors) == 1

    assert await async_unload_entry(hass, config_entry)


async def test_offline_poll_error_log_kept_by_default(hass, caplog):
    """Without quiet mode the coordinator still logs offline polls as errors."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="loud_offline_poll"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
    ):
        await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert any(
        record.levelno == logging.ERROR
        and "Error fetching moonraker data" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


async def test_send_data_unreachable_raises_update_failed(hass, caplog):
    """Sending data to an unreachable printer fails with a warning log."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="send_unreachable"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        caplog.at_level(logging.DEBUG),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)

    assert any(
        record.levelno == logging.WARNING
        and "connection to moonraker down" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


async def test_quiet_mode_keeps_error_log_for_other_failures(hass, caplog):
    """Quiet mode must not hide refresh failures unrelated to reachability."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_other_failure",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ),
        caplog.at_level(logging.DEBUG),
    ):
        await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert any(
        record.levelno == logging.ERROR
        and "Error fetching moonraker data" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


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

    device_id = [
        device.id
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
    ]

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

    device_ids = [
        device.id
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
    ]
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


@pytest.mark.parametrize(
    ("result", "message"),
    [
        ({"error": {"code": 400, "message": "Must home"}}, "Must home"),
        ({"error": {"code": 400}}, "unknown error"),
        # A power device named "error" answers with its status
        ({"error": "on"}, None),
        ({"printer": "on"}, None),
        ("ok", None),
        (None, None),
    ],
)
def test_moonraker_error_message(result, message):
    """Only Moonraker's error object counts as an error."""
    assert _moonraker_error_message(result) == message


async def test_send_gcode_reports_klipper_error(hass):
    """A rejected script fails the action with Klipper's message, not the script."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="gcode_error"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_id = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0].id

    # moonraker-api returns the error as the call's result instead of raising
    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value={"error": {"code": 400, "message": "Must home axis first"}},
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {"device_id": device_id, "gcode": ["G28 X", "G1 X10"]},
            blocking=True,
        )
    assert str(err.value) == "G-code failed on mainsail: Must home axis first"
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("first_result", "first_message"),
    [
        ({"error": {"code": 400, "message": "Must home"}}, "Must home"),
        (Exception("connection lost"), "could not send the command"),
    ],
)
async def test_send_gcode_failure_does_not_stop_other_printers(
    hass, first_result, first_message
):
    """Every printer receives the script, and the error names those that failed."""

    entries = [
        MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id=f"printer_{i}")
        for i in (1, 2)
    ]
    dev_reg = dr.async_get(hass)
    device_ids = []
    for entry in entries:
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        device = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)[0]
        dev_reg.async_update_device(device.id, name_by_user=entry.entry_id)
        device_ids.append(device.id)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=[first_result, {"result": "ok"}],
        ) as mock_call,
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {"device_id": device_ids, "gcode": "G28"},
            blocking=True,
        )

    assert mock_call.await_count == 2
    assert str(err.value) == f"G-code failed on printer_1: {first_message}"
    for entry in entries:
        assert await async_unload_entry(hass, entry)


async def test_send_gcode_error_names_all_failed_printers(hass):
    """Each failed printer is listed, using the entry title without a device."""

    entries = [
        MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id=f"printer_{i}")
        for i in (1, 2)
    ]
    for entry in entries:
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=[
                {"error": {"code": 400, "message": "First"}},
                {"error": {"code": 400, "message": "Second"}},
            ],
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {"device_id": [entry.entry_id for entry in entries], "gcode": "G28"},
            blocking=True,
        )

    assert str(err.value) == "G-code failed on mainsail: First; mainsail: Second"
    for entry in entries:
        assert await async_unload_entry(hass, entry)


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data"),
    [
        ("button", "press", "button.mainsail_emergency_stop", {}),
        ("number", "set_value", "number.mainsail_bed_target", {"value": 50}),
        ("number", "set_value", "number.mainsail_output_pin_pwm", {"value": 10}),
        ("switch", "turn_on", "switch.mainsail_output_pin_digital", {}),
        ("switch", "turn_on", "switch.mainsail_printer", {}),
        ("light", "turn_on", "light.mainsail_led_chamber", {"brightness": 77}),
        ("light", "turn_off", "light.mainsail_led_chamber", {}),
    ],
)
async def test_entity_reports_rejected_command(hass, domain, service, entity_id, data):
    """Entities fail with Moonraker's message and keep their previous state."""

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="rejected")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    before = hass.states.get(entity_id)
    assert before is not None

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            return_value={"error": {"code": 400, "message": "Rejected by Klipper"}},
        ),
        pytest.raises(HomeAssistantError, match="^Rejected by Klipper$"),
    ):
        await hass.services.async_call(
            domain, service, {"entity_id": entity_id, **data}, blocking=True
        )
    await hass.async_block_till_done()

    # HA records a button's last press even when the press fails
    if domain != "button":
        # Write the state again, as attributes held by the entity must not have
        # changed either: the next write would show a value the printer rejected.
        hass.data[domain].get_entity(entity_id).async_write_ha_state()
        after = hass.states.get(entity_id)
        assert after.state == before.state
        assert after.attributes == before.attributes

    assert await async_unload_entry(hass, config_entry)


async def _setup_gcode_printer(hass):
    """Set up a printer and return its config entry and device id."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="no_wait")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]
    return config_entry, device.id


async def _call_send_gcode(hass, device_id, **data):
    await hass.services.async_call(
        DOMAIN,
        "send_gcode",
        {"device_id": device_id, "gcode": "LONG_MACRO", **data},
        blocking=True,
    )


async def test_send_gcode_reports_timeout(hass):
    """A timed out script fails, saying the printer may still be running it."""
    config_entry, device_id = await _setup_gcode_printer(hass)

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
        pytest.raises(HomeAssistantError, match="may still be running the command"),
    ):
        await _call_send_gcode(hass, device_id)

    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("outcome", "log_level", "logged"),
    [
        ({"result": "ok"}, None, None),
        (
            {"error": {"code": 400, "message": "Macro failed"}},
            "ERROR",
            "G-code failed on mainsail: Macro failed",
        ),
        (Exception("connection lost"), "ERROR", "the connection was lost"),
        (TimeoutError(), "DEBUG", "may still be running the command"),
    ],
)
async def test_send_gcode_no_wait_returns_while_running(
    hass, caplog, outcome, log_level, logged
):
    """With wait off, the action returns and later outcomes go to the log."""
    caplog.set_level(logging.DEBUG, logger="custom_components.moonraker")
    config_entry, device_id = await _setup_gcode_printer(hass)
    finish = asyncio.Event()

    async def _long_command(*_args, **_kwargs):
        await finish.wait()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with (
        patch("custom_components.moonraker.GCODE_REJECT_WINDOW", 0.01),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=_long_command,
        ) as mock_call,
    ):
        await _call_send_gcode(hass, device_id, wait=False)
        assert not finish.is_set()
        mock_call.assert_awaited_once_with(
            METHODS.PRINTER_GCODE_SCRIPT.value, script="LONG_MACRO"
        )
        finish.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    records = [
        r
        for r in caplog.records
        if r.getMessage().startswith(("G-code failed", "Stopped waiting"))
    ]
    if log_level is None:
        assert not records
    else:
        assert any(
            r.levelname == log_level and logged in r.getMessage() for r in records
        )
        assert log_level == "ERROR" or not any(r.levelname == "ERROR" for r in records)

    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (None, None),
        (
            {"error": {"code": 400, "message": "Must home"}},
            "G-code failed on mainsail: Must home",
        ),
    ],
)
async def test_send_gcode_no_wait_reports_immediate_result(hass, result, error):
    """With wait off, an immediate rejection still fails the action."""
    config_entry, device_id = await _setup_gcode_printer(hass)

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        return_value=result,
    ):
        if error is None:
            await _call_send_gcode(hass, device_id, wait=False)
        else:
            with pytest.raises(HomeAssistantError) as err:
                await _call_send_gcode(hass, device_id, wait=False)
            assert str(err.value) == error

    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_no_wait_cancelled_on_unload(hass, caplog):
    """Unloading the entry cancels a script left running, without logging an error."""
    config_entry, device_id = await _setup_gcode_printer(hass)
    cancelled = asyncio.Event()

    async def _never_finishes(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with (
        patch("custom_components.moonraker.GCODE_REJECT_WINDOW", 0.01),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=_never_finishes,
        ),
    ):
        await _call_send_gcode(hass, device_id, wait=False)
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

    assert cancelled.is_set()
    assert "G-code failed" not in caplog.text


async def test_send_gcode_no_wait_action_cancelled_still_logs(hass, caplog):
    """Cancelling the action leaves the script running, and its error is logged."""
    config_entry, device_id = await _setup_gcode_printer(hass)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def _long_command(*_args, **_kwargs):
        started.set()
        await finish.wait()
        return {"error": {"code": 400, "message": "Macro failed"}}

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        side_effect=_long_command,
    ):
        action = asyncio.create_task(_call_send_gcode(hass, device_id, wait=False))
        await started.wait()
        action.cancel()
        with pytest.raises(asyncio.CancelledError):
            await action
        assert "G-code failed" not in caplog.text

        finish.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert "G-code failed on mainsail: Macro failed" in caplog.text
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("wait", "max_running"),
    [(True, 1), (False, 2)],
)
async def test_send_gcode_several_printers_order(hass, wait, max_running):
    """With wait off printers get the script together, with it on one at a time."""
    entries = [
        MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id=f"printer_{i}")
        for i in (1, 2)
    ]
    for entry in entries:
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    running = 0
    most_running = 0

    async def _command(*_args, **_kwargs):
        nonlocal running, most_running
        running += 1
        most_running = max(most_running, running)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        running -= 1
        return {"result": "ok"}

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        new_callable=AsyncMock,
        side_effect=_command,
    ) as mock_call:
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [entry.entry_id for entry in entries],
                "gcode": "G28",
                "wait": wait,
            },
            blocking=True,
        )

    assert mock_call.await_count == 2
    assert most_running == max_running
    for entry in entries:
        assert await async_unload_entry(hass, entry)


async def test_send_gcode_no_wait_names_failed_printers(hass):
    """With wait off, every printer that rejects the script is named, in order."""
    entries = [
        MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id=f"printer_{i}")
        for i in (1, 2)
    ]
    for entry in entries:
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=[
                {"error": {"code": 400, "message": "First"}},
                {"error": {"code": 400, "message": "Second"}},
            ],
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [entry.entry_id for entry in entries],
                "gcode": "G28",
                "wait": False,
            },
            blocking=True,
        )

    assert str(err.value) == "G-code failed on mainsail: First; mainsail: Second"
    for entry in entries:
        assert await async_unload_entry(hass, entry)


async def test_send_gcode_wait_as_text(hass):
    """Text such as "false" counts as off, and an invalid value sends nothing."""
    config_entry, device_id = await _setup_gcode_printer(hass)
    finish = asyncio.Event()

    async def _long_command(*_args, **_kwargs):
        await finish.wait()
        return {"result": "ok"}

    with (
        patch("custom_components.moonraker.GCODE_REJECT_WINDOW", 0.01),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            new_callable=AsyncMock,
            side_effect=_long_command,
        ) as mock_call,
    ):
        with pytest.raises(vol.Invalid):
            await _call_send_gcode(hass, device_id, wait="sometimes")
        mock_call.assert_not_awaited()

        await _call_send_gcode(hass, device_id, wait="false")
        assert not finish.is_set()
        mock_call.assert_awaited_once()

        finish.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert await async_unload_entry(hass, config_entry)


async def test_send_gcode_empty_payload_skips_send(hass):
    """Ensure empty payloads do not call Moonraker."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="empty_payload"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_ids = [
        device.id
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
    ]

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

    device_ids = [
        device.id
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
    ]
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
        config_entry_id=None,
        identifiers={(DOMAIN, config_entry.entry_id)},
        name="mainsail",
        name_by_user=None,
    )

    def async_get_override(device_id):
        if device_id == identifier_device_id:
            return identifier_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
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


async def test_send_gcode_legacy_config_entries(hass):
    """Use config_entries on devices without config_entry_id (HA before 2026.8)."""

    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="legacy_config_entries"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    original_async_get = dev_reg.async_get
    legacy_device_id = "legacy-device"
    legacy_device = SimpleNamespace(
        config_entries={config_entry.entry_id},
        identifiers=set(),
        name="mainsail",
        name_by_user=None,
    )

    def async_get_override(device_id):
        if device_id == legacy_device_id:
            return legacy_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_gcode",
            {
                "device_id": [legacy_device_id],
                "gcode": "M115",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_call.assert_awaited_once_with(
        METHODS.PRINTER_GCODE_SCRIPT.value, script="M115"
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
        config_entry_id=None,
        identifiers=set(),
    )

    def async_get_override(device_id):
        if device_id == orphan_device_id:
            return orphan_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
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
        config_entry_id="ghost-entry",
        identifiers=set(),
    )

    def async_get_override(device_id):
        if device_id == missing_device_id:
            return missing_device
        return original_async_get(device_id)

    with (
        patch.object(dev_reg, "async_get", side_effect=async_get_override),
        patch(
            "moonraker_api.MoonrakerClient.call_method", new_callable=AsyncMock
        ) as mock_call,
    ):
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
    from pytest_homeassistant.common import MockConfigEntry
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
    from pytest_homeassistant.common import MockConfigEntry
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


async def test_setup_while_klippy_not_ready(hass):
    """Setup succeeds when Moonraker answers every query with an error."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            return_value={
                "error": {"code": 503, "message": "Klippy Host not connected"}
            },
        ),
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state.value == "loaded"
    assert hass.states.get("sensor.1_2_3_4_printer_state").state == "unavailable"
    for sensor in ("print_speed", "progress", "current_layer", "object_height"):
        assert hass.states.get(f"sensor.1_2_3_4_{sensor}").state == "unavailable"


async def _setup_polling_entry(hass, entry_id, options=None):
    """Set up an entry with the given options and return its coordinator."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, options=options or {}, entry_id=entry_id
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    return hass.data[DOMAIN][config_entry.entry_id]


async def test_polling_rate_option_survives_first_refresh(hass, get_data):
    """The configured rate is used when idle, also after the first refresh."""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    coordinator = await _setup_polling_entry(
        hass, "test_rate", {CONF_OPTION_POLLING_RATE: 10}
    )

    assert coordinator.update_interval == timedelta(seconds=10)

    with patch.object(coordinator, "_schedule_refresh"):
        get_data["status"]["print_stats"]["state"] = PRINTSTATES.PRINTING.value
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=2)

        get_data["status"]["print_stats"]["state"] = PRINTSTATES.COMPLETE.value
        await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=10)


async def test_polling_rate_faster_than_print_rate_is_kept(hass, get_data):
    """A configured rate faster than 2 s is not slowed down while printing."""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    coordinator = await _setup_polling_entry(
        hass, "test_fast", {CONF_OPTION_POLLING_RATE: 1}
    )

    with patch.object(coordinator, "_schedule_refresh"):
        get_data["status"]["print_stats"]["state"] = PRINTSTATES.PRINTING.value
        await coordinator._async_update_data()

    assert coordinator.update_interval == timedelta(seconds=1)


async def test_polling_rate_is_per_entry(hass, get_data):
    """Each printer keeps its own configured rate."""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    first = await _setup_polling_entry(
        hass, "test_first", {CONF_OPTION_POLLING_RATE: 15}
    )
    second = await _setup_polling_entry(
        hass, "test_second", {CONF_OPTION_POLLING_RATE: 45}
    )

    assert first.update_interval == timedelta(seconds=15)
    assert second.update_interval == timedelta(seconds=45)


@pytest.mark.parametrize("rate", [0, -5, "fast", None])
async def test_invalid_polling_rate_uses_default(hass, get_data, rate):
    """An unusable saved rate falls back to 30 seconds."""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    coordinator = await _setup_polling_entry(
        hass, "test_invalid", {CONF_OPTION_POLLING_RATE: rate}
    )

    assert coordinator.update_interval == timedelta(seconds=30)


async def test_failed_first_refresh_stops_client(hass):
    """A setup that fails its first refresh closes the websocket."""
    with (
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            side_effect=load_data,
        ),
        patch(
            "custom_components.moonraker.MoonrakerApiClient.stop",
            new_callable=AsyncMock,
        ) as mock_stop,
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, config_entry)

    mock_stop.assert_awaited_once()


async def test_unload_stops_client(hass):
    """Unloading an entry closes its websocket."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    with patch(
        "custom_components.moonraker.MoonrakerApiClient.stop",
        new_callable=AsyncMock,
    ) as mock_stop:
        assert await async_unload_entry(hass, config_entry)

    mock_stop.assert_awaited_once()


@pytest.mark.parametrize("send", [False, True])
async def test_reconnect_failure_raises_update_failed(hass, send):
    """A failed reconnect is reported as a failed update, not a crash."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "moonraker_api.MoonrakerClient.is_connected",
            new_callable=PropertyMock,
            return_value=False,
        ),
        patch(
            "custom_components.moonraker.MoonrakerApiClient.start",
            side_effect=ConnectionError("refused"),
        ),
        pytest.raises(UpdateFailed, match="could not reconnect"),
    ):
        if send:
            await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)
        else:
            await coordinator.async_fetch_data(METHODS.PRINTER_INFO)

    assert await async_unload_entry(hass, config_entry)


async def test_setup_runs_a_single_full_update(hass, get_default_api_response):
    """Platform setup fetches only new data instead of full updates."""
    calls = []

    async def call_method(method, **kwargs):
        calls.append((method, kwargs))
        return get_default_api_response

    with patch("moonraker_api.MoonrakerClient.call_method", side_effect=call_method):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    methods = [method for method, _ in calls]
    # Once while connecting, once by the first (and only) full update.
    assert methods.count("printer.info") == 2
    assert methods.count("printer.objects.list") == 1
    config_queries = [
        kwargs
        for method, kwargs in calls
        if method == "printer.objects.query"
        and kwargs.get("objects") == {"configfile": ["settings"]}
    ]
    assert len(config_queries) == 1
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("query", "fetched", "missing"),
    [
        ({"a": None}, {}, {"a": None}),
        ({"a": ["x"]}, {}, {"a": ["x"]}),
        ({"a": ["x"]}, {"a": None}, {}),
        ({"a": None}, {"a": ["x"]}, {"a": None}),
        ({"a": ["x", "y"]}, {"a": ["x"]}, {"a": ["y"]}),
        ({"a": ["x"]}, {"a": ["x"]}, {}),
    ],
)
def test_query_difference(query, fetched, missing):
    """Only objects and fields not fetched yet are returned."""
    assert _query_difference(query, fetched) == missing


@pytest.mark.parametrize(
    ("fetched", "query", "merged"),
    [
        ({}, {"a": None}, {"a": None}),
        ({"a": ["x"]}, {"a": None}, {"a": None}),
        ({"a": None}, {"a": ["x"]}, {"a": None}),
        ({"a": ["x"]}, {"a": ["x", "y"]}, {"a": ["x", "y"]}),
        ({}, {"a": ["x"]}, {"a": ["x"]}),
    ],
)
def test_merge_query(fetched, query, merged):
    """Fetched queries are recorded without duplicates."""
    _merge_query(fetched, query)
    assert fetched == merged


async def _setup_coordinator(hass):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry, hass.data[DOMAIN][config_entry.entry_id]


async def test_refresh_new_data_merges_new_fields(hass):
    """New fields are merged into existing status objects."""
    config_entry, coordinator = await _setup_coordinator(hass)
    coordinator.data["status"]["extruder"] = {"temperature": 200.0}
    coordinator.add_query_objects("extruder", "pressure_advance")
    coordinator.add_query_objects("new_object", None)

    with patch.object(
        coordinator,
        "_async_fetch_data",
        AsyncMock(
            return_value={
                "status": {
                    "extruder": {"pressure_advance": 0.04},
                    "new_object": {"value": 1},
                }
            }
        ),
    ) as fetch:
        await coordinator.async_refresh_new_data()
        await coordinator.async_refresh_new_data()

    fetch.assert_awaited_once_with(
        METHODS.PRINTER_OBJECTS_QUERY,
        {"objects": {"extruder": ["pressure_advance"], "new_object": None}},
    )
    assert coordinator.data["status"]["extruder"] == {
        "temperature": 200.0,
        "pressure_advance": 0.04,
    }
    assert coordinator.data["status"]["new_object"] == {"value": 1}
    assert await async_unload_entry(hass, config_entry)


async def test_refresh_new_data_runs_new_updaters_once(hass):
    """An updater added during setup runs once, before its entities are added."""
    config_entry, coordinator = await _setup_coordinator(hass)
    updater = AsyncMock(return_value={"extra": {"value": 1}})
    coordinator.add_data_updater(updater)

    await coordinator.async_refresh_new_data()
    await coordinator.async_refresh_new_data()

    updater.assert_awaited_once_with(coordinator)
    assert coordinator.data["extra"] == {"value": 1}
    assert await async_unload_entry(hass, config_entry)


async def test_refresh_new_data_failure_retries_later(hass):
    """A failed fetch keeps the data and is retried on the next call."""
    config_entry, coordinator = await _setup_coordinator(hass)
    data = coordinator.data
    coordinator.add_query_objects("new_object", None)

    with patch.object(
        coordinator, "_async_fetch_data", AsyncMock(side_effect=UpdateFailed("down"))
    ) as fetch:
        await coordinator.async_refresh_new_data()
        await coordinator.async_refresh_new_data()

    assert fetch.await_count == 2
    assert coordinator.data is data
    assert await async_unload_entry(hass, config_entry)


async def test_refresh_new_data_without_data_runs_full_refresh(hass):
    """Without data yet, a full refresh is run instead."""
    config_entry, coordinator = await _setup_coordinator(hass)
    coordinator.data = None

    with patch.object(coordinator, "async_refresh", AsyncMock()) as refresh:
        await coordinator.async_refresh_new_data()

    refresh.assert_awaited_once()
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("getter", "method"),
    [
        ("async_get_printer_objects_list", METHODS.PRINTER_OBJECTS_LIST),
        ("async_get_config_settings", METHODS.PRINTER_OBJECTS_QUERY),
    ],
)
async def test_setup_cache_skips_error_results(hass, getter, method):
    """An error result is returned but not cached."""
    config_entry, coordinator = await _setup_coordinator(hass)
    coordinator._printer_objects_list = None
    coordinator._config_settings = None

    with patch.object(
        coordinator,
        "async_fetch_data",
        AsyncMock(side_effect=[{"error": "not ready"}, {"objects": []}]),
    ) as fetch:
        assert await getattr(coordinator, getter)() == {"error": "not ready"}
        assert await getattr(coordinator, getter)() == {"objects": []}
        assert await getattr(coordinator, getter)() == {"objects": []}

    assert fetch.await_count == 2
    assert fetch.await_args_list[0].args[0] == method
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize("send", [False, True])
async def test_stopped_client_is_not_restarted(hass, send):
    """A refresh still running after unload stopped the client doesn't reconnect."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    coordinator.moonraker.stopped = True

    with (
        patch(
            "moonraker_api.MoonrakerClient.is_connected",
            new_callable=PropertyMock,
            return_value=False,
        ),
        patch(
            "custom_components.moonraker.MoonrakerApiClient.start",
            new_callable=AsyncMock,
        ) as start,
        pytest.raises(UpdateFailed, match="client is stopped"),
    ):
        if send:
            await coordinator.async_send_data(METHODS.PRINTER_EMERGENCY_STOP)
        else:
            await coordinator.async_fetch_data(METHODS.PRINTER_INFO)

    start.assert_not_awaited()
    coordinator.moonraker.stopped = False
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize("quiet", [False, True])
async def test_reconnect_failure_when_host_went_offline(hass, quiet):
    """A reconnect that fails because the printer went offline counts as unreachable."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: quiet},
        entry_id="test",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with (
        patch(
            "moonraker_api.MoonrakerClient.is_connected",
            new_callable=PropertyMock,
            return_value=False,
        ),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            side_effect=[True, False],
        ),
        patch(
            "custom_components.moonraker.MoonrakerApiClient.start",
            side_effect=ConnectionError("refused"),
        ),
        pytest.raises(UpdateFailed, match="is unreachable") as err,
    ):
        await coordinator.async_fetch_data(METHODS.PRINTER_INFO)

    assert (type(err.value) is UpdateFailed) is (not quiet)
    assert await async_unload_entry(hass, config_entry)
