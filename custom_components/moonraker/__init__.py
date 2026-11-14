"""Moonraker integration for Home Assistant."""

import asyncio
import logging
from contextlib import suppress
from functools import partial
import os.path
import uuid
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MoonrakerApiClient
from .const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_TLS,
    CONF_URL,
    DEFAULT_POLLING_RATE,
    DEFAULT_PORT,
    DEVICE_TYPE,
    DOMAIN,
    HOSTNAME,
    METHODS,
    MIN_POLLING_RATE,
    OBJ,
    PLATFORMS,
    PRINTING_POLLING_RATE,
    TIMEOUT,
    PRINTSTATES,
)
from .sensor import SENSORS

# How long send_gcode with wait: false waits for the printer to reject a script
GCODE_REJECT_WINDOW = 5

# Only checks wait: Home Assistant adds the action's target fields to the data
SEND_GCODE_SCHEMA = vol.Schema(
    {vol.Optional("wait", default=True): cv.boolean}, extra=vol.ALLOW_EXTRA
)

_LOGGER = logging.getLogger(__name__)

_LOGGER.debug("loading moonraker init")

_GCODE_ROOT = "gcodes"


def _quiet_unreachable_logs(entry: ConfigEntry) -> bool:
    """Return whether unreachable Moonraker connection logs should be debug-only."""
    return entry.options.get(CONF_OPTION_QUIET_UNREACHABLE, False)


def _entry_polling_interval(entry: ConfigEntry) -> timedelta:
    """Return the polling interval configured for an entry."""
    try:
        polling_rate = int(
            entry.options.get(CONF_OPTION_POLLING_RATE, DEFAULT_POLLING_RATE)
        )
    except (TypeError, ValueError):
        polling_rate = DEFAULT_POLLING_RATE
    if polling_rate < MIN_POLLING_RATE:
        polling_rate = DEFAULT_POLLING_RATE
    return timedelta(seconds=polling_rate)


def _log_unreachable(entry: ConfigEntry, message: str, *args: Any) -> None:
    """Log unreachable-device messages at the configured verbosity."""
    if _quiet_unreachable_logs(entry):
        _LOGGER.debug(message, *args)
    else:
        _LOGGER.warning(message, *args)


class _QuietUnreachableUpdateFailed(UpdateFailed):
    """Refresh failure caused by an unreachable printer in quiet mode.

    Only refreshes aborted by this exception skip the coordinator failure
    log; any other failure keeps its error level.
    """


def _normalize_moonraker_port(port: int | str | None) -> int:
    """Return the effective Moonraker port used at runtime."""
    if port is None or port == "":
        return DEFAULT_PORT
    return int(port)


def _entry_port(entry: ConfigEntry) -> int:
    """Return the effective Moonraker port for a config entry."""
    return _normalize_moonraker_port(entry.data.get(CONF_PORT, DEFAULT_PORT))


async def _async_is_tcp_reachable(host: str, port: int | str | None) -> bool:
    """Return whether a TCP connection to the Moonraker endpoint can be opened."""
    writer: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(TIMEOUT):
            _reader, writer = await asyncio.open_connection(
                host, _normalize_moonraker_port(port)
            )
        return True
    except (asyncio.TimeoutError, OSError, TypeError, ValueError):
        return False
    finally:
        if writer is not None:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


async def async_setup(_hass: HomeAssistant, _config: ConfigType):
    """Set up this integration using YAML is not supported."""
    return True


def _normalize_gcode_path(filename: str | None) -> tuple[str, str | None]:
    """Return normalized filename and detected root for gcode metadata calls."""
    if not filename:
        return "", None

    normalized = filename.replace("\\", "/").strip()
    if not normalized:
        return "", None

    normalized = normalized.lstrip("/")
    lowered = normalized.casefold()

    root = None
    root_prefix = f"{_GCODE_ROOT}/"
    if lowered.startswith(root_prefix):
        root = _GCODE_ROOT
        normalized = normalized[len(root_prefix) :]
    else:
        marker = f"/{_GCODE_ROOT}/"
        idx = lowered.find(marker)
        if idx != -1:
            root = _GCODE_ROOT
            normalized = normalized[idx + len(marker) :]

    return normalized, root


def _strip_gcode_root(path: str | None, root: str | None) -> str:
    """Strip a known root prefix from a path for URL usage."""
    if not path:
        return ""

    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return ""

    normalized = normalized.lstrip("/")
    if not root:
        root_prefix = f"{_GCODE_ROOT}/"
        lowered = normalized.casefold()
        if lowered.startswith(root_prefix):
            return normalized[len(root_prefix) :]
        return normalized

    lowered = normalized.casefold()
    root_prefix = f"{root}/"
    if lowered.startswith(root_prefix):
        return normalized[len(root_prefix) :]

    marker = f"/{root}/"
    idx = lowered.find(marker)
    if idx != -1:
        return normalized[idx + len(marker) :]

    return normalized


def _build_thumbnail_path(
    gcode_dir: str, thumbnail_path: str | None, root: str | None
) -> str | None:
    """Build a thumbnail path relative to the gcodes root."""
    normalized = _strip_gcode_root(thumbnail_path, root)
    if not normalized:
        return None

    if normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return None

    if not gcode_dir:
        return normalized

    gcode_dir = gcode_dir.replace("\\", "/").strip("/")
    if not gcode_dir:
        return normalized

    if normalized.startswith(f"{gcode_dir}/"):
        return normalized

    return os.path.join(gcode_dir, normalized)


def get_user_name(hass: HomeAssistant, entry: ConfigEntry):
    """Get username."""
    device_registry = dr.async_get(hass)
    device_entries = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    if len(device_entries) < 1:
        return None

    return device_entries[0].name_by_user


def _moonraker_error_message(result: Any) -> str | None:
    """Return the error message in a Moonraker call result, if any.

    moonraker-api returns errors as the call's result ({"error": {...}}) instead
    of raising them. Only that object form is an error: a power device named
    "error" legitimately answers {"error": "on"}.
    """
    error = result.get("error") if isinstance(result, dict) else None
    if not isinstance(error, dict):
        return None
    return str(error.get("message") or "unknown error")


class _CommandTimedOut(UpdateFailed):
    """Moonraker didn't answer in time, which doesn't mean the command failed."""


def _log_background_gcode_result(name: str, task: asyncio.Task) -> None:
    """Log how a G-code script that was left running in the background ended."""
    if task.cancelled():
        return
    err = task.exception()
    if isinstance(err, _CommandTimedOut):
        _LOGGER.debug("Stopped waiting for G-code on %s: %s", name, err)
    elif err is not None:
        _LOGGER.error(
            "G-code failed on %s: %s", name, str(err) or "the connection was lost"
        )


async def _async_send_gcode(
    hass: HomeAssistant, coordinator, script: str, name: str, wait: bool
) -> None:
    """Send a script, without waiting for it to finish if wait is off.

    With wait off, return if the printer hasn't rejected the script after a
    while, and leave it running in the background.
    """
    send = coordinator.async_send_data(METHODS.PRINTER_GCODE_SCRIPT, {"script": script})
    if wait:
        await send
        return
    task = coordinator.config_entry.async_create_background_task(
        hass, send, f"moonraker send_gcode {name}"
    )
    done: set[asyncio.Task] = set()
    try:
        done, _ = await asyncio.wait({task}, timeout=GCODE_REJECT_WINDOW)
    finally:
        # Also when the action is cancelled, as the script carries on regardless
        if not done:
            task.add_done_callback(partial(_log_background_gcode_result, name))
    if done:
        task.result()


async def _async_send_gcode_to_printers(
    hass: HomeAssistant, targets: list[tuple[Any, str]], script: str, wait: bool
) -> list[str]:
    """Send a script to each (coordinator, name) and return the failures."""

    async def _send(coordinator, name: str) -> str | None:
        try:
            await _async_send_gcode(hass, coordinator, script, name, wait)
        except HomeAssistantError as err:
            # Keep going so one failing printer doesn't stop the others
            return f"{name}: {str(err) or 'could not send the command'}"
        return None

    if wait:
        results = [await _send(*target) for target in targets]
    else:
        # Don't make one printer's reject window delay the next printer
        results = await asyncio.gather(*(_send(*target) for target in targets))
    return [failure for failure in results if failure]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""

    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})

    custom_name = get_user_name(hass, entry)

    url = entry.data.get(CONF_URL)
    port = _entry_port(entry)
    tls = entry.data.get(CONF_TLS, False)
    api_key = entry.data.get(CONF_API_KEY, "")
    printer_name = (
        entry.data.get(CONF_PRINTER_NAME) if custom_name is None else custom_name
    )

    api = MoonrakerApiClient(
        url,
        async_get_clientsession(hass, verify_ssl=False),
        port=port,
        api_key=api_key,
        tls=tls,
    )

    try:
        if not await _async_is_tcp_reachable(url, port):
            _log_unreachable(
                entry,
                "Cannot configure moonraker instance: %s:%s is unreachable",
                url,
                port,
            )
            raise ConfigEntryNotReady(f"Error connecting to {url}:{port}")

        async with asyncio.timeout(TIMEOUT):
            await api.start()
            printer_info = await api.client.call_method("printer.info")
            _LOGGER.debug(printer_info)

            api_device_name = (
                printer_name
                or printer_info.get(HOSTNAME)
                or printer_info.get(DEVICE_TYPE)
                or url
            )

            hass.config_entries.async_update_entry(entry, title=api_device_name)

    except ConfigEntryNotReady:
        await api.stop()
        raise
    except Exception as exc:
        _LOGGER.warning("Cannot configure moonraker instance")
        await api.stop()
        raise ConfigEntryNotReady(f"Error connecting to {url}:{port}") from exc

    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=api, config_entry=entry, api_device_name=api_device_name
    )

    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        await api.stop()
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator
    for platform in PLATFORMS:
        coordinator.platforms.append(platform)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def send_gcode_service(service_call):
        """Handle the service call to send g-code."""
        gcode = service_call.data["gcode"]
        raw_device_ids = service_call.data["device_id"]
        wait = service_call.data["wait"]
        dev_reg = dr.async_get(hass)

        if isinstance(gcode, list):
            script = "\n".join(line for line in gcode if line)
        else:
            script = str(gcode)

        if not script.strip():
            _LOGGER.warning("Received empty G-code payload, skipping send")
            return

        if isinstance(raw_device_ids, str):
            device_ids = [raw_device_ids]
        else:
            device_ids = list(raw_device_ids)

        processed_entries: set[str] = set()
        targets: list[tuple[Any, str]] = []

        domain_entries = hass.data.get(DOMAIN, {})

        for device_id in device_ids:
            device = dev_reg.async_get(device_id)
            entry_ids: set[str] = set()

            if device is None:
                if device_id in domain_entries:
                    entry_ids.add(device_id)
                else:
                    _LOGGER.warning("Unknown Moonraker device_id %s", device_id)
                    continue
            else:
                if hasattr(device, "config_entry_id"):
                    if device.config_entry_id:
                        entry_ids.add(device.config_entry_id)
                else:
                    # HA before 2026.8 has no DeviceEntry.config_entry_id.
                    entry_ids.update(getattr(device, "config_entries", None) or ())
                if not entry_ids:
                    for domain, identifier in device.identifiers:
                        if domain == DOMAIN:
                            entry_ids.add(identifier)

            if not entry_ids:
                _LOGGER.warning(
                    "Moonraker device %s has no associated config entries", device_id
                )
                continue

            for entry_id in entry_ids:
                if entry_id not in hass.data.get(DOMAIN, {}):
                    _LOGGER.warning(
                        "Moonraker device %s entry %s not loaded",
                        device_id,
                        entry_id,
                    )
                    continue

                if entry_id in processed_entries:
                    continue

                processed_entries.add(entry_id)

                _LOGGER.debug(
                    "Sending G-code via entry %s for device %s", entry_id, device_id
                )

                coordinator = hass.data[DOMAIN][entry_id]
                name = (
                    device and (device.name_by_user or device.name)
                ) or coordinator.config_entry.title
                targets.append((coordinator, name))

        failures = await _async_send_gcode_to_printers(hass, targets, script, wait)
        if failures:
            raise HomeAssistantError(f"G-code failed on {'; '.join(failures)}")

    # Register the new service
    hass.services.async_register(
        DOMAIN, "send_gcode", send_gcode_service, schema=SEND_GCODE_SCHEMA
    )

    return True


def _copy_query(query: dict[str, list[str] | None]) -> dict[str, list[str] | None]:
    """Copy a printer object query so later changes don't affect the copy."""
    return {obj: None if keys is None else list(keys) for obj, keys in query.items()}


def _query_difference(
    query: dict[str, list[str] | None], fetched: dict[str, list[str] | None]
) -> dict[str, list[str] | None]:
    """Return the part of ``query`` that ``fetched`` doesn't cover yet."""
    missing: dict[str, list[str] | None] = {}
    for obj, keys in query.items():
        if obj not in fetched:
            missing[obj] = None if keys is None else list(keys)
            continue
        fetched_keys = fetched[obj]
        if fetched_keys is None:
            continue
        if keys is None:
            missing[obj] = None
            continue
        new_keys = [key for key in keys if key not in fetched_keys]
        if new_keys:
            missing[obj] = new_keys
    return missing


def _merge_query(
    fetched: dict[str, list[str] | None], query: dict[str, list[str] | None]
) -> None:
    """Record that ``query`` has now been fetched."""
    for obj, keys in query.items():
        if keys is None:
            fetched[obj] = None
            continue
        fetched_keys = fetched.setdefault(obj, [])
        if fetched_keys is None:
            continue
        fetched_keys.extend(key for key in keys if key not in fetched_keys)


async def _printer_objects_updater(coordinator):
    return await coordinator._async_fetch_data(
        METHODS.PRINTER_OBJECTS_QUERY, coordinator.query_obj
    )


async def _printer_info_updater(coordinator):
    return {
        "printer.info": await coordinator._async_fetch_data(METHODS.PRINTER_INFO, None)
    }


async def _gcode_file_detail_updater(coordinator):
    data = await coordinator._async_fetch_data(
        METHODS.PRINTER_OBJECTS_QUERY, coordinator.query_obj
    )
    filename = ""
    status = data.get("status") or {}
    print_stats = status.get("print_stats") or {}
    filename = print_stats.get("filename") or ""
    if not filename:
        virtual_sdcard = status.get("virtual_sdcard") or {}
        filename = virtual_sdcard.get("file_path") or ""

    return await coordinator._async_get_gcode_file_detail(filename)


class MoonrakerDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MoonrakerApiClient,
        config_entry: ConfigEntry,
        api_device_name: str,
    ) -> None:
        """Initialize."""
        self.moonraker = client
        self.platforms = []
        self.updaters = [
            _printer_objects_updater,
            _printer_info_updater,
            _gcode_file_detail_updater,
        ]
        self.hass = hass
        self.config_entry = config_entry
        self.api_device_name = api_device_name
        self.polling_interval = _entry_polling_interval(config_entry)
        self.query_obj = {OBJ: {}}
        # What the last update fetched, so platform setup can fetch only
        # what it adds (see async_refresh_new_data).
        self._fetched_updaters: set = set()
        self._fetched_query: dict[str, list[str] | None] = {}
        self._new_data_lock = asyncio.Lock()
        # Printer objects and config settings, fetched once per setup and
        # shared by the platforms.
        self._printer_objects_list: dict[str, Any] | None = None
        self._config_settings: dict[str, Any] | None = None
        self._setup_cache_lock = asyncio.Lock()
        self.load_sensor_data(SENSORS)
        self.add_query_objects("virtual_sdcard", "file_path")

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self.polling_interval,
            config_entry=config_entry,
        )

    async def _async_refresh(self, log_failures: bool = True, *args, **kwargs):
        """Refresh data, keeping unreachable failures quiet when configured."""
        if not _quiet_unreachable_logs(self.config_entry):
            return await super()._async_refresh(log_failures, *args, **kwargs)

        was_successful = self.last_update_success
        await super()._async_refresh(False, *args, **kwargs)
        err = self.last_exception
        if (
            log_failures
            and was_successful
            and not self.last_update_success
            and isinstance(err, (UpdateFailed, TimeoutError))
            and not isinstance(err, _QuietUnreachableUpdateFailed)
        ):
            self.logger.error("Error fetching %s data: %s", self.name, err)

    async def _async_update_data(self):
        """Update data via library."""
        # Platform setup merges new data in async_refresh_new_data. Run one at a
        # time, so an update that started earlier can't overwrite that data.
        async with self._new_data_lock:
            return await self._async_fetch_all_data()

    async def _async_fetch_all_data(self):
        """Run every data updater and return the combined data."""
        data = {}
        updaters = list(self.updaters)
        query = _copy_query(self.query_obj[OBJ])

        for updater in updaters:
            data.update(await updater(self))

        data.setdefault("status", {})
        self._fetched_updaters = set(updaters)
        self._fetched_query = query

        # --- Dynamic polling logic ---
        prev_state = getattr(self, "_last_print_state", None)
        current_state = data.get("status", {}).get("print_stats", {}).get("state")
        if current_state != prev_state:
            if current_state == PRINTSTATES.PRINTING.value:
                self.update_interval = min(
                    self.polling_interval, timedelta(seconds=PRINTING_POLLING_RATE)
                )
            else:
                self.update_interval = self.polling_interval
            self._schedule_refresh()
        self._last_print_state = current_state
        # --- end dynamic polling logic ---

        return data

    async def _async_get_gcode_file_detail(self, gcode_filename):
        return_gcode = {
            "thumbnails_path": None,
            "estimated_time": 1,
            "filament_total": 1,
            "layer_count": None,
            "layer_height": None,
            "object_height": None,
            "first_layer_height": None,
            "gcode_start_byte": None,
            "gcode_end_byte": None,
        }
        if not gcode_filename:
            return return_gcode

        # Get prefix of the filename to get the appropriate thumbnail
        normalized_filename, root = _normalize_gcode_path(gcode_filename)
        if not normalized_filename:
            return return_gcode

        dirname = os.path.dirname(normalized_filename)

        query_object = {"filename": normalized_filename}
        gcode = await self._async_fetch_data(
            METHODS.SERVER_FILES_METADATA, query_object
        )
        return_gcode["estimated_time"] = gcode.get("estimated_time", 0)
        return_gcode["object_height"] = gcode.get("object_height", 0)
        return_gcode["filament_total"] = gcode.get("filament_total", 0)
        return_gcode["layer_count"] = gcode.get("layer_count", 0)
        return_gcode["layer_height"] = gcode.get("layer_height", 0)
        return_gcode["first_layer_height"] = gcode.get("first_layer_height", 0)
        return_gcode["gcode_start_byte"] = gcode.get("gcode_start_byte")
        return_gcode["gcode_end_byte"] = gcode.get("gcode_end_byte")

        thumbnails = gcode.get("thumbnails")
        if not thumbnails or not isinstance(thumbnails, list):
            return return_gcode

        best_path = None
        best_size = -1.0
        for thumbnail in thumbnails:
            if not isinstance(thumbnail, dict):
                continue
            relative_path = thumbnail.get("relative_path")
            if not relative_path:
                continue
            size = thumbnail.get("size")
            size_value = None
            if size is not None:
                try:
                    size_value = float(size)
                except (TypeError, ValueError):
                    size_value = None

            if size_value is None:
                if best_path is None:
                    best_path = relative_path
                continue

            if size_value > best_size:
                best_size = size_value
                best_path = relative_path

        if not best_path:
            return return_gcode

        return_gcode["thumbnails_path"] = _build_thumbnail_path(
            dirname, best_path, root
        )
        return return_gcode

    async def _async_fetch_data(
        self, query_path: METHODS, query_object, quiet: bool = False
    ):
        myuuid = str(uuid.uuid4())
        _LOGGER.debug(f"fetching data, uuid: {myuuid}, from: {query_path.value}")
        _LOGGER.debug(f"fetching, uuid: {myuuid}, object: {query_object}")
        if not self.moonraker.client.is_connected:
            if not await _async_is_tcp_reachable(
                self.config_entry.data.get(CONF_URL),
                _entry_port(self.config_entry),
            ):
                _log_unreachable(
                    self.config_entry,
                    "connection to moonraker down; %s:%s is unreachable",
                    self.config_entry.data.get(CONF_URL),
                    _entry_port(self.config_entry),
                )
                raise self._unreachable_error()
            await self._async_restart_client()
        try:
            if query_object is None:
                result = await self.moonraker.client.call_method(query_path.value)
            else:
                result = await self.moonraker.client.call_method(
                    query_path.value, **query_object
                )
            if not quiet:
                _LOGGER.debug(f"Query Result, uuid: {myuuid}: {result}")
            return result
        except Exception as exception:
            # The websocket may still look connected right after the printer
            # went offline, so recheck reachability before reporting.
            if _quiet_unreachable_logs(
                self.config_entry
            ) and not await _async_is_tcp_reachable(
                self.config_entry.data.get(CONF_URL),
                _entry_port(self.config_entry),
            ):
                raise self._unreachable_error() from exception
            raise UpdateFailed() from exception

    async def _async_restart_client(self) -> None:
        """Reconnect the websocket, reporting a failure as a failed update."""
        if self.moonraker.stopped:
            # The entry stopped the client while unloading. A refresh that was
            # already running must not open a websocket that nothing closes.
            raise UpdateFailed("moonraker client is stopped")
        _LOGGER.warning("connection to moonraker down, restarting")
        try:
            await self.moonraker.start()
        except Exception as exception:
            if not await _async_is_tcp_reachable(
                self.config_entry.data.get(CONF_URL),
                _entry_port(self.config_entry),
            ):
                raise self._unreachable_error() from exception
            raise UpdateFailed(
                f"could not reconnect to moonraker: {exception!r}"
            ) from exception

    def _unreachable_error(self) -> UpdateFailed:
        """Build the refresh failure for an unreachable Moonraker endpoint."""
        error = (
            f"{self.config_entry.data.get(CONF_URL)}:"
            f"{_entry_port(self.config_entry)} is unreachable"
        )
        if _quiet_unreachable_logs(self.config_entry):
            return _QuietUnreachableUpdateFailed(error)
        return UpdateFailed(error)

    async def _async_send_data(self, query_path: METHODS, query_obj) -> None:
        if not self.moonraker.client.is_connected:
            if not await _async_is_tcp_reachable(
                self.config_entry.data.get(CONF_URL),
                _entry_port(self.config_entry),
            ):
                _log_unreachable(
                    self.config_entry,
                    "connection to moonraker down; %s:%s is unreachable",
                    self.config_entry.data.get(CONF_URL),
                    _entry_port(self.config_entry),
                )
                raise UpdateFailed(
                    f"{self.config_entry.data.get(CONF_URL)}:"
                    f"{_entry_port(self.config_entry)} is unreachable"
                )
            await self._async_restart_client()
        try:
            if query_obj is None:
                result = await self.moonraker.client.call_method(query_path.value)
            else:
                result = await self.moonraker.client.call_method(
                    query_path.value, **query_obj
                )
        except TimeoutError as exception:
            raise _CommandTimedOut(
                "timed out waiting for the printer, which may still be running "
                "the command"
            ) from exception
        except Exception as exception:
            raise UpdateFailed() from exception
        if message := _moonraker_error_message(result):
            raise HomeAssistantError(message)

    async def async_fetch_data(
        self,
        query_path: METHODS,
        query_obj: dict[str, Any] | None = None,
        quiet: bool = False,
    ):
        """Fetch data from moonraker."""
        return await self._async_fetch_data(query_path, query_obj, quiet=quiet)

    async def async_send_data(
        self, query_path: METHODS, query_obj: dict[str, Any] | None = None
    ):
        """Send data to moonraker."""
        return await self._async_send_data(query_path, query_obj)

    async def async_get_printer_objects_list(self) -> dict[str, Any]:
        """Return the printer object list, fetched once per setup."""
        async with self._setup_cache_lock:
            if self._printer_objects_list is not None:
                return self._printer_objects_list
            result = await self.async_fetch_data(METHODS.PRINTER_OBJECTS_LIST)
            if isinstance(result, dict) and not result.get("error"):
                self._printer_objects_list = result
            return result

    async def async_get_config_settings(self) -> dict[str, Any]:
        """Return the configfile settings query result, fetched once per setup."""
        async with self._setup_cache_lock:
            if self._config_settings is not None:
                return self._config_settings
            result = await self.async_fetch_data(
                METHODS.PRINTER_OBJECTS_QUERY,
                {OBJ: {"configfile": ["settings"]}},
                quiet=True,
            )
            if isinstance(result, dict) and not result.get("error"):
                self._config_settings = result
            return result

    async def async_refresh_new_data(self) -> None:
        """Fetch only the data added since the last update and merge it in.

        Platform setup adds query objects and data updaters, and its entities
        need that data. Fetching just the new part, instead of running a full
        update for each platform, keeps setup to a single full update.
        """
        if self.data is None:
            await self.async_refresh()
            return

        async with self._new_data_lock:
            updaters = [
                updater
                for updater in self.updaters
                if updater not in self._fetched_updaters
            ]
            query = _query_difference(self.query_obj[OBJ], self._fetched_query)
            if not updaters and not query:
                return

            new_data = {}
            try:
                for updater in updaters:
                    new_data.update(await updater(self))
                if query:
                    result = await self._async_fetch_data(
                        METHODS.PRINTER_OBJECTS_QUERY, {OBJ: query}
                    )
                else:
                    result = {}
            except UpdateFailed as err:
                _LOGGER.debug("Could not fetch data for new entities: %s", err)
                return
            if query and (not isinstance(result, dict) or "status" not in result):
                # A Moonraker error response: leave it to be fetched again.
                _LOGGER.debug("Could not fetch data for new entities: %s", result)
                return

            data = dict(self.data)
            status = dict(data.get("status", {}))
            data.update(new_data)
            for obj, values in (result.get("status") or {}).items():
                if isinstance(values, dict) and isinstance(status.get(obj), dict):
                    status[obj] = {**status[obj], **values}
                else:
                    status[obj] = values
            data["status"] = status
            self.data = data
            self._fetched_updaters.update(updaters)
            _merge_query(self._fetched_query, query)
        self.async_update_listeners()

    def add_data_updater(self, updater):
        """Update the data."""
        self.updaters.append(updater)

    def load_sensor_data(self, sensor_list):
        """Load sensor data, so we can poll the right object."""
        for sensor in sensor_list:
            for subscriptions in sensor.subscriptions:
                self.add_query_objects(subscriptions[0], subscriptions[1])

    def add_query_objects(self, query_object: str, result_key: str | None):
        """Build the list of object we want to retreive from the server."""
        if result_key is None:
            self.query_obj[OBJ][query_object] = None
            return

        if (
            query_object in self.query_obj[OBJ]
            and self.query_obj[OBJ][query_object] is None
        ):
            return

        if query_object not in self.query_obj[OBJ]:
            self.query_obj[OBJ][query_object] = []
        if result_key not in self.query_obj[OBJ][query_object]:
            self.query_obj[OBJ][query_object].append(result_key)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        await coordinator.moonraker.stop()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    hass.data[DOMAIN][entry.entry_id].config_entry = entry
    await hass.config_entries.async_reload(entry.entry_id)
