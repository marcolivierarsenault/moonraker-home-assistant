"""Moonraker integration for Home Assistant."""

import asyncio
from collections.abc import Callable
import logging
from contextlib import suppress
import os.path
import uuid
from datetime import timedelta
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
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
    DEFAULT_POLLING_RATE,
    MIN_POLLING_RATE,
    NOTIFY_KLIPPY_DISCONNECTED,
    NOTIFY_KLIPPY_READY,
    NOTIFY_KLIPPY_SHUTDOWN,
    NOTIFY_STATUS_UPDATE,
    PRINTING_POLLING_RATE,
    PUSH_UPDATE_INTERVAL,
    CONF_TLS,
    CONF_URL,
    DEFAULT_PORT,
    DEVICE_TYPE,
    DOMAIN,
    HOSTNAME,
    METHODS,
    OBJ,
    PLATFORMS,
    TIMEOUT,
    PRINTSTATES,
)
from .sensor import SENSORS

_PRINTING_SCAN_INTERVAL = timedelta(seconds=PRINTING_POLLING_RATE)

_LOGGER = logging.getLogger(__name__)

_LOGGER.debug("loading moonraker init")

_GCODE_ROOT = "gcodes"


def _quiet_unreachable_logs(entry: ConfigEntry) -> bool:
    """Return whether unreachable Moonraker connection logs should be debug-only."""
    return entry.options.get(CONF_OPTION_QUIET_UNREACHABLE, False)


def _log_unreachable(entry: ConfigEntry, message: str, *args: Any) -> None:
    """Log unreachable-device messages at the configured verbosity."""
    if _quiet_unreachable_logs(entry):
        _LOGGER.debug(message, *args)
    else:
        _LOGGER.warning(message, *args)


def _normalize_moonraker_port(port: int | str | None) -> int:
    """Return the effective Moonraker port used at runtime."""
    if port is None or port == "":
        return DEFAULT_PORT
    return int(port)


def _entry_port(entry: ConfigEntry) -> int:
    """Return the effective Moonraker port for a config entry."""
    return _normalize_moonraker_port(entry.data.get(CONF_PORT, DEFAULT_PORT))


def _entry_polling_interval(entry: ConfigEntry) -> timedelta:
    """Return a safe per-entry polling interval."""
    try:
        polling_rate = int(
            entry.options.get(CONF_OPTION_POLLING_RATE, DEFAULT_POLLING_RATE)
        )
    except (TypeError, ValueError):
        polling_rate = DEFAULT_POLLING_RATE
    return timedelta(seconds=max(polling_rate, MIN_POLLING_RATE))


async def _async_is_tcp_reachable(host: str, port: int | str | None) -> bool:
    """Return whether a TCP connection to the Moonraker endpoint can be opened."""
    writer: asyncio.StreamWriter | None = None
    try:
        async with async_timeout.timeout(TIMEOUT):
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

        async with async_timeout.timeout(TIMEOUT):
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

    try:
        await coordinator.async_subscribe_status_updates()
    except UpdateFailed:
        _LOGGER.warning(
            "Could not subscribe to Moonraker status updates; polling only"
        )

    async def send_gcode_service(service_call):
        """Handle the service call to send g-code."""
        gcode = service_call.data["gcode"]
        raw_device_ids = service_call.data["device_id"]
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
                if getattr(device, "config_entries", None):
                    entry_ids.update(device.config_entries)
                if device.primary_config_entry:
                    entry_ids.add(device.primary_config_entry)
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

                await hass.data[DOMAIN][entry_id].async_send_data(
                    METHODS.PRINTER_GCODE_SCRIPT,
                    {"script": script},
                )

    # Register the new service
    hass.services.async_register(DOMAIN, "send_gcode", send_gcode_service)

    return True


def _extract_gcode_filename(status: dict[str, Any]) -> str:
    """Return the active G-code filename from a status payload."""
    print_stats = status.get("print_stats") or {}
    filename = print_stats.get("filename") or ""
    if not filename:
        virtual_sdcard = status.get("virtual_sdcard") or {}
        filename = virtual_sdcard.get("file_path") or ""
    return filename


async def _printer_objects_updater(coordinator):
    data = await coordinator._async_fetch_objects()
    filename = _extract_gcode_filename(data.get("status") or {})
    return {**data, **await coordinator._async_get_gcode_file_detail(filename)}


async def _printer_info_updater(coordinator):
    return {
        "printer.info": await coordinator._async_fetch_data(METHODS.PRINTER_INFO, None)
    }


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
        self.updaters = [_printer_objects_updater, _printer_info_updater]
        self.hass = hass
        self.config_entry = config_entry
        self.api_device_name = api_device_name
        self.polling_interval = _entry_polling_interval(config_entry)
        self.query_obj = {OBJ: {}}
        self._queried_objects: dict[str, set[str] | None] = {}
        self._query_refresh_lock = asyncio.Lock()
        self._printer_objects_list: dict[str, Any] | None = None
        self._printer_objects_lock = asyncio.Lock()
        self._config_settings: dict[str, Any] | None = None
        self._config_settings_lock = asyncio.Lock()
        self._system_info: dict[str, Any] | None = None
        self._system_info_lock = asyncio.Lock()
        self._gcode_metadata_cache_key: tuple[str, str | None] | None = None
        self._gcode_metadata_cache: dict[str, Any] | None = None
        self._subscribed_to_status = False
        self._push_unsub: Callable[[], None] | None = None
        self._updater_every: dict[Any, int] = {}
        self._update_cycle = 0
        client.notification_handler = self._async_handle_notification
        self.load_sensor_data(SENSORS)
        self.add_query_objects("virtual_sdcard", "file_path")

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self.polling_interval,
            config_entry=config_entry,
        )

    async def _async_update_data(self):
        """Update data via library."""
        data = dict(self.data or {})

        for updater in self.updaters:
            if self._update_cycle % self._updater_every.get(updater, 1) == 0:
                data.update(await updater(self))
        self._update_cycle += 1

        self._update_polling_interval(data)

        return data

    def _update_polling_interval(self, data: dict[str, Any]) -> None:
        """Adjust the poll cadence when the print state changes."""
        prev_state = getattr(self, "_last_print_state", None)
        current_state = data.get("status", {}).get("print_stats", {}).get("state")
        if current_state == prev_state:
            return
        if current_state in (PRINTSTATES.PRINTING.value, PRINTSTATES.PAUSED.value):
            self.update_interval = _PRINTING_SCAN_INTERVAL
        else:
            self.update_interval = self.polling_interval
        self._schedule_refresh()
        self._last_print_state = current_state

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

        cache_key = (normalized_filename, root)
        if (
            cache_key == self._gcode_metadata_cache_key
            and self._gcode_metadata_cache is not None
        ):
            return self._gcode_metadata_cache.copy()

        dirname = os.path.dirname(normalized_filename)
        query_object = {"filename": normalized_filename}
        try:
            gcode = await self._async_fetch_data(
                METHODS.SERVER_FILES_METADATA, query_object
            )
        except UpdateFailed:
            _LOGGER.debug("Could not retrieve metadata for current G-code file")
            self._gcode_metadata_cache_key = cache_key
            self._gcode_metadata_cache = return_gcode
            return return_gcode.copy()
        return_gcode["estimated_time"] = gcode.get("estimated_time", 0)
        return_gcode["object_height"] = gcode.get("object_height", 0)
        return_gcode["filament_total"] = gcode.get("filament_total", 0)
        return_gcode["layer_count"] = gcode.get("layer_count", 0)
        return_gcode["layer_height"] = gcode.get("layer_height", 0)
        return_gcode["first_layer_height"] = gcode.get("first_layer_height", 0)
        return_gcode["gcode_start_byte"] = gcode.get("gcode_start_byte")
        return_gcode["gcode_end_byte"] = gcode.get("gcode_end_byte")

        thumbnails = gcode.get("thumbnails")
        if isinstance(thumbnails, list):
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

            if best_path:
                return_gcode["thumbnails_path"] = _build_thumbnail_path(
                    dirname, best_path, root
                )

        self._gcode_metadata_cache_key = cache_key
        self._gcode_metadata_cache = return_gcode
        return return_gcode.copy()

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
                raise UpdateFailed()
            _LOGGER.warning("connection to moonraker down, restarting")
            try:
                async with async_timeout.timeout(TIMEOUT):
                    await self.moonraker.start()
                    await self._async_resubscribe()
            except Exception as exception:
                raise UpdateFailed() from exception
        try:
            async with async_timeout.timeout(TIMEOUT):
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
            raise UpdateFailed() from exception

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
                raise UpdateFailed()
            _LOGGER.warning("connection to moonraker down, restarting")
            try:
                async with async_timeout.timeout(TIMEOUT):
                    await self.moonraker.start()
                    await self._async_resubscribe()
            except Exception as exception:
                raise UpdateFailed() from exception
        try:
            if query_obj is None:
                await self.moonraker.client.call_method(query_path.value)
            else:
                await self.moonraker.client.call_method(query_path.value, **query_obj)
        except Exception as exception:
            raise UpdateFailed() from exception

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

    async def async_get_printer_objects(self):
        """Return the printer object list, fetching it at most once per setup."""
        if self._printer_objects_list is None:
            async with self._printer_objects_lock:
                if self._printer_objects_list is None:
                    self._printer_objects_list = await self._async_fetch_data(
                        METHODS.PRINTER_OBJECTS_LIST, None
                    )
        return self._printer_objects_list

    async def async_get_config_settings(self):
        """Return printer configuration settings, fetching them once per setup."""
        if self._config_settings is None:
            async with self._config_settings_lock:
                if self._config_settings is None:
                    self._config_settings = await self._async_fetch_data(
                        METHODS.PRINTER_OBJECTS_QUERY,
                        {OBJ: {"configfile": ["settings"]}},
                        quiet=True,
                    )
        return self._config_settings

    async def async_get_system_info(self):
        """Return Moonraker system information, fetching it once per setup."""
        if self._system_info is None:
            async with self._system_info_lock:
                if self._system_info is None:
                    self._system_info = await self._async_fetch_data(
                        METHODS.MACHINE_SYSTEM_INFO, None, quiet=True
                    )
        return self._system_info

    def set_initial_data(self, key: str, value: Any) -> None:
        """Add setup-time data without triggering a full coordinator refresh."""
        self.data = {**(self.data or {}), key: value}

    async def _async_fetch_objects(
        self, query_objects: dict[str, Any] | None = None, quiet: bool = False
    ):
        if query_objects is None:
            query_objects = {
                object_name: None if properties is None else list(properties)
                for object_name, properties in self.query_obj[OBJ].items()
            }
        data = await self._async_fetch_data(
            METHODS.PRINTER_OBJECTS_QUERY, {OBJ: query_objects}, quiet=quiet
        )
        self._record_queried_objects(query_objects)
        return data

    def _record_queried_objects(self, query_objects: dict[str, Any]) -> None:
        for object_name, properties in query_objects.items():
            if properties is None:
                self._queried_objects[object_name] = None
            elif object_name not in self._queried_objects:
                self._queried_objects[object_name] = set(properties)
            elif self._queried_objects[object_name] is not None:
                self._queried_objects[object_name].update(properties)

    def _get_unqueried_objects(self) -> dict[str, Any]:
        query_objects = {}
        for object_name, properties in self.query_obj[OBJ].items():
            if object_name not in self._queried_objects:
                query_objects[object_name] = (
                    None if properties is None else list(properties)
                )
                continue
            queried_properties = self._queried_objects[object_name]
            if queried_properties is None:
                continue
            if properties is None:
                query_objects[object_name] = None
                continue
            new_properties = [
                property_name
                for property_name in properties
                if property_name not in queried_properties
            ]
            if new_properties:
                query_objects[object_name] = new_properties
        return query_objects

    def _subscription_objects(self) -> dict[str, Any]:
        """Return the object field map used for status subscriptions."""
        return {
            object_name: None if properties is None else list(properties)
            for object_name, properties in self.query_obj[OBJ].items()
        }

    async def async_subscribe_status_updates(self) -> None:
        """Subscribe to Moonraker status notifications for tracked objects."""
        query_objects = self._subscription_objects()
        if not query_objects:
            return
        result = await self._async_fetch_data(
            METHODS.PRINTER_OBJECTS_SUBSCRIBE, {OBJ: query_objects}, quiet=True
        )
        self._subscribed_to_status = True
        pushed = result.get("objects") if isinstance(result, dict) else None
        if not isinstance(pushed, dict) and isinstance(result, dict):
            pushed = result.get("status")
        if isinstance(pushed, dict):
            self._merge_status_update(pushed)

    async def _async_resubscribe(self) -> None:
        """Restore the status subscription after a reconnect."""
        if not self._subscribed_to_status:
            return
        query_objects = self._subscription_objects()
        if not query_objects:
            return
        try:
            async with async_timeout.timeout(TIMEOUT):
                await self.moonraker.client.call_method(
                    METHODS.PRINTER_OBJECTS_SUBSCRIBE.value,
                    objects=query_objects,
                )
        except Exception:
            _LOGGER.debug("Could not restore Moonraker status subscription")

    @staticmethod
    def _status_delta(data: Any) -> dict[str, Any]:
        """Extract changed status objects from a notification payload."""
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        if isinstance(data, dict):
            status = data.get("status")
            if isinstance(status, dict):
                return status
            return data
        return {}

    def _merge_status_update(self, status_delta: dict[str, Any]) -> bool:
        """Merge pushed status changes into coordinator data."""
        current_data = dict(self.data or {})
        status = dict(current_data.get("status") or {})
        changed = False
        for object_name, object_data in status_delta.items():
            current_object_data = status.get(object_name)
            if isinstance(object_data, dict) and isinstance(current_object_data, dict):
                merged = {**current_object_data, **object_data}
                if merged != current_object_data:
                    status[object_name] = merged
                    changed = True
            elif current_object_data != object_data:
                status[object_name] = object_data
                changed = True
        if changed:
            current_data["status"] = status
            self.data = current_data
        return changed

    async def _async_handle_notification(self, method: str, data: Any) -> None:
        """Handle a Moonraker push notification."""
        if method == NOTIFY_KLIPPY_READY:
            await self.async_request_refresh()
            return
        if method in (NOTIFY_KLIPPY_DISCONNECTED, NOTIFY_KLIPPY_SHUTDOWN):
            reason = method.removeprefix("notify_klippy_")
            self.async_set_update_error(UpdateFailed(f"Klippy {reason}"))
            return
        if method != NOTIFY_STATUS_UPDATE:
            return
        status_delta = self._status_delta(data)
        if not status_delta:
            return
        status = (self.data or {}).get("status") or {}
        previous_state = (status.get("print_stats") or {}).get("state")
        if not self._merge_status_update(status_delta):
            return
        new_state = ((self.data.get("status") or {}).get("print_stats") or {}).get(
            "state"
        )
        if new_state != previous_state:
            await self._async_flush_push_data()
        else:
            self._schedule_push_flush()

    def _schedule_push_flush(self) -> None:
        """Debounce pushed updates into a single entity dispatch."""
        if self._push_unsub is not None:
            return
        self._push_unsub = async_call_later(
            self.hass,
            timedelta(seconds=PUSH_UPDATE_INTERVAL),
            self._async_flush_push_data,
        )

    async def _async_flush_push_data(self, _now: Any = None) -> None:
        """Dispatch merged push data to entities."""
        if self._push_unsub is not None:
            self._push_unsub()
            self._push_unsub = None
        if self.data is None:
            return
        self._update_polling_interval(self.data)
        status = self.data.get("status") or {}
        filename = _extract_gcode_filename(status)
        cache_key = _normalize_gcode_path(filename) if filename else None
        self.async_update_listeners()
        if filename and cache_key != self._gcode_metadata_cache_key:
            await self.async_request_refresh()

    def async_shutdown_push_updates(self) -> None:
        """Detach notification handling and cancel pending push dispatch."""
        self.moonraker.notification_handler = None
        if self._push_unsub is not None:
            self._push_unsub()
            self._push_unsub = None

    async def async_refresh_query_data(self) -> None:
        """Fetch newly requested status fields without refreshing unrelated data."""
        async with self._query_refresh_lock:
            query_objects = self._get_unqueried_objects()
            if not query_objects:
                return
            query_data = await self._async_fetch_objects(query_objects, quiet=True)
            current_data = dict(self.data or {})
            status = dict(current_data.get("status") or {})
            for object_name, object_data in (query_data.get("status") or {}).items():
                current_object_data = status.get(object_name)
                if isinstance(object_data, dict) and isinstance(
                    current_object_data, dict
                ):
                    status[object_name] = {**current_object_data, **object_data}
                else:
                    status[object_name] = object_data
            current_data.update(query_data)
            current_data["status"] = status
            self.data = current_data

    def add_data_updater(self, updater, every: int = 1):
        """Add a data updater; ``every`` runs it once per N poll cycles."""
        self.updaters.append(updater)
        if every > 1:
            self._updater_every[updater] = every

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
        coordinator.async_shutdown_push_updates()
        await coordinator.moonraker.stop()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    hass.data[DOMAIN][entry.entry_id].config_entry = entry
    await hass.config_entries.async_reload(entry.entry_id)
