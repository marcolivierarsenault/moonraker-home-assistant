"""Test moonraker setup process."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
    _QuietUnreachableLogFilter,
    _async_is_tcp_reachable,
    _build_thumbnail_path,
    _normalize_gcode_path,
    _normalize_moonraker_port,
    _strip_gcode_root,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.moonraker.const import (
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
        record.levelno == logging.DEBUG
        and "Error fetching moonraker data" in record.getMessage()
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


async def test_coordinator_logger_filters_do_not_accumulate(hass):
    """Recreating a coordinator must not stack filters or drop foreign ones."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="filter_hygiene"
    )

    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )
    foreign_filter = logging.Filter("foreign")
    coordinator.logger.addFilter(foreign_filter)

    recreated = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="printer"
    )

    assert recreated.logger is coordinator.logger
    assert foreign_filter in recreated.logger.filters
    quiet_filters = [
        log_filter
        for log_filter in recreated.logger.filters
        if isinstance(log_filter, _QuietUnreachableLogFilter)
    ]
    assert len(quiet_filters) == 1
    assert quiet_filters[0].coordinator is recreated

    recreated.logger.removeFilter(foreign_filter)
    recreated.detach_log_filter()


def _quiet_filters(logger):
    """Return the quiet-mode filters currently attached to a logger."""
    return [
        log_filter
        for log_filter in logger.filters
        if isinstance(log_filter, _QuietUnreachableLogFilter)
    ]


async def test_quiet_mode_keeps_error_log_after_out_of_refresh_failure(hass, caplog):
    """A failed fetch outside a refresh must not demote a later error."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_out_of_refresh",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Platforms call async_fetch_data() outside of _async_update_data(); an
    # unreachable printer there must not arm the quiet-mode downgrade.
    with (
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)

    assert not coordinator.quiet_unreachable_failure

    with caplog.at_level(logging.DEBUG):
        coordinator.logger.error("unrelated failure")

    assert any(
        record.levelno == logging.ERROR and "unrelated failure" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


async def test_quiet_flag_cleared_when_refresh_ends(hass, caplog):
    """The quiet-failure flag must not survive the refresh that raised it."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_QUIET_UNREACHABLE: True},
        entry_id="quiet_flag_scope",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    with patch(
        "custom_components.moonraker._async_is_tcp_reachable",
        new_callable=AsyncMock,
        return_value=False,
    ):
        # The second refresh emits no record at all (the coordinator only logs
        # the first failure), so nothing consumes the flag.
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not coordinator.quiet_unreachable_failure

    with caplog.at_level(logging.DEBUG):
        coordinator.logger.error("unrelated failure")

    assert any(
        record.levelno == logging.ERROR and "unrelated failure" in record.getMessage()
        for record in caplog.records
    )

    assert await async_unload_entry(hass, config_entry)


async def test_log_filter_detached_on_unload(hass):
    """Unloading an entry must not leave the filter on the process logger."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="filter_unload"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    logger = coordinator.logger
    assert _quiet_filters(logger)

    assert await async_unload_entry(hass, config_entry)

    assert not _quiet_filters(logger)
    assert coordinator.quiet_log_filter is None

    # Detaching again is a no-op.
    coordinator.detach_log_filter()
    assert not _quiet_filters(logger)


async def test_log_filter_detached_when_setup_fails(hass):
    """A coordinator that never finishes setup must release its filter."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, entry_id="filter_setup_failure"
    )
    config_entry.add_to_hass(hass)

    logger = logging.getLogger(
        f"custom_components.moonraker.coordinator.{config_entry.entry_id}"
    )

    with (
        patch(
            "custom_components.moonraker.MoonrakerDataUpdateCoordinator._async_update_data",
            new_callable=AsyncMock,
            side_effect=UpdateFailed("boom"),
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, config_entry)

    assert not _quiet_filters(logger)


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
        config_entries={"ghost-entry"},
        primary_config_entry=None,
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
