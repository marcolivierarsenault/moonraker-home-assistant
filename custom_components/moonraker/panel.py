"""Live control panel views for the Moonraker integration."""

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import aiohttp
import async_timeout
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_PORT,
    CONF_TLS,
    CONF_URL,
    DEFAULT_PORT,
    DOMAIN,
    METHODS,
    PRINTING_POLLING_RATE,
    TIMEOUT,
    VERSION,
)

if TYPE_CHECKING:
    from . import MoonrakerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "/api/moonraker/panel"
PANEL_EMBED_URL = "/api/moonraker/panel_embed"
PANEL_MODULE_URL = "/api/moonraker/panel_module.js"
PANEL_CLIENT_URL = "/api/moonraker/panel_client.js"
PANEL_DATA_URL = "/api/moonraker/panel_data"
PANEL_GCODE_URL = "/api/moonraker/panel_gcode"
PANEL_THUMB_URL = "/api/moonraker/panel_thumbnail"
PANEL_ACTION_URL = "/api/moonraker/panel_action"
PANEL_FRONTEND_PATH = "moonraker-control-deck"
UPLOAD_URL = "/api/moonraker/gcode_upload"

_GCODE_ROOT = "gcodes"
_MAX_TOOLPATH_BYTES = 128 * 1024 * 1024
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "panel.html")
_MODULE_PATH = os.path.join(os.path.dirname(__file__), "panel_module.js")
_CLIENT_PATH = os.path.join(os.path.dirname(__file__), "panel_client.js")

_META_KEYS = (
    "estimated_time",
    "filament_total",
    "layer_count",
    "layer_height",
    "first_layer_height",
    "object_height",
    "thumbnails_path",
    "gcode_start_byte",
    "gcode_end_byte",
)

_DIRECT_ACTIONS = {
    "pause": METHODS.PRINTER_PRINT_PAUSE,
    "resume": METHODS.PRINTER_PRINT_RESUME,
    "cancel": METHODS.PRINTER_PRINT_CANCEL,
    "emergency_stop": METHODS.PRINTER_EMERGENCY_STOP,
    "firmware_restart": METHODS.PRINTER_FIRMWARE_RESTART,
    "server_restart": METHODS.SERVER_RESTART,
    "host_restart": METHODS.HOST_RESTART,
    "host_shutdown": METHODS.HOST_SHUTDOWN,
    "machine_update_refresh": METHODS.MACHINE_UPDATE_REFRESH,
    "start_queue": METHODS.SERVER_JOB_QUEUE_START,
}

_GCODE_ACTIONS = {
    "set_speed": "M220 S{}",
    "set_flow": "M221 S{}",
    "set_fan": "M106 S{}",
    "set_extruder": "M104 S{}",
    "set_bed": "M140 S{}",
    "z_adjust": "SET_GCODE_OFFSET Z_ADJUST={}",
    "z_set": "SET_GCODE_OFFSET Z={}",
    "motors_off": "M84",
    "cooldown": "M104 S0\nM140 S0\nM107",
    "home_x": "G28 X",
    "home_y": "G28 Y",
    "home_z": "G28 Z",
    "home_all": "G28",
}

_PREHEAT_PRESETS = {
    "pla": (200, 60),
    "petg": (240, 80),
    "abs": (245, 100),
}


def _read_asset(path: str) -> str:
    """Read a panel asset from disk; intended to run in the executor."""
    with open(path, encoding="utf-8") as file:
        return file.read()


def _entry_port(entry) -> int:
    """Return the effective Moonraker port for a config entry."""
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    return int(port) if port not in (None, "") else DEFAULT_PORT


def _webcam_url(entry, url: str | None) -> str | None:
    """Resolve a Moonraker webcam URL to an absolute URL."""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    scheme = "https" if entry.data.get(CONF_TLS, False) else "http"
    host = entry.data.get(CONF_URL)
    port = _entry_port(entry)
    return f"{scheme}://{host}:{port}/{url.lstrip('/')}"


class _PanelViewBase(HomeAssistantView):
    """Shared helpers for panel views."""

    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        self.hass = hass

    def _coordinators(self) -> dict[str, "MoonrakerDataUpdateCoordinator"]:
        from . import MoonrakerDataUpdateCoordinator

        return {
            entry_id: coordinator
            for entry_id, coordinator in self.hass.data.get(DOMAIN, {}).items()
            if isinstance(coordinator, MoonrakerDataUpdateCoordinator)
        }

    def _resolve(self, entry_id: str | None):
        coordinators = self._coordinators()
        if entry_id:
            return coordinators.get(entry_id)
        return next(iter(coordinators.values()), None)


class MoonrakerPanelView(HomeAssistantView):
    """Redirect the legacy panel URL to the authenticated HA sidebar panel."""

    url = PANEL_URL
    name = "api:moonraker:panel"
    requires_auth = False

    async def get(self, request):
        """Redirect to the Home Assistant frontend panel."""
        return web.Response(
            status=302, headers={"Location": f"/{PANEL_FRONTEND_PATH}"}
        )


class MoonrakerPanelEmbedView(HomeAssistantView):
    """Serve the control deck page within the authenticated HA panel."""

    url = PANEL_EMBED_URL
    name = "api:moonraker:panel_embed"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        self.hass = hass
        self._template: str | None = None

    async def get(self, request):
        """Render the panel content frame."""
        if self._template is None:
            self._template = await self.hass.async_add_executor_job(
                _read_asset, _TEMPLATE_PATH
            )
        return web.Response(text=self._template, content_type="text/html")


class _PanelAssetView(HomeAssistantView):
    """Serve static panel code, which contains no printer data or credentials."""

    requires_auth = False

    def __init__(self, hass: HomeAssistant, path: str) -> None:
        """Initialize the asset view."""
        self.hass = hass
        self._path = path

    async def get(self, request):
        """Serve a static panel asset."""
        content = await self.hass.async_add_executor_job(_read_asset, self._path)
        return web.Response(
            text=content,
            content_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )


class MoonrakerPanelModuleView(_PanelAssetView):
    """Serve the Home Assistant custom panel module."""

    url = PANEL_MODULE_URL
    name = "api:moonraker:panel_module"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        super().__init__(hass, _MODULE_PATH)


class MoonrakerPanelClientView(_PanelAssetView):
    """Serve the panel's browser-side control logic."""

    url = PANEL_CLIENT_URL
    name = "api:moonraker:panel_client"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        super().__init__(hass, _CLIENT_PATH)


class MoonrakerUploadRedirectView(HomeAssistantView):
    """Redirect browser navigation to the upload UI in the control panel."""

    url = UPLOAD_URL
    name = "api:moonraker:gcode_upload_page"
    requires_auth = False

    async def get(self, request):
        """Redirect to the authenticated Home Assistant panel."""
        return web.Response(
            status=302, headers={"Location": f"/{PANEL_FRONTEND_PATH}"}
        )


class MoonrakerPanelDataView(_PanelViewBase):
    """Return a JSON snapshot of coordinator data for the panel."""

    url = PANEL_DATA_URL
    name = "api:moonraker:panel_data"

    async def get(self, request):
        """Return the current coordinator data snapshot."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return self.json({"error": "no printer configured"}, status_code=404)

        data = coordinator.data or {}
        status = data.get("status") or {}
        file_list = data.get("file_list") or {}
        files = file_list.get("files") if isinstance(file_list, dict) else file_list
        if not isinstance(files, list):
            files = []

        webcams = []
        try:
            webcam_result = await coordinator.async_get_webcams()
        except Exception:  # noqa: BLE001 - webcams are optional
            webcam_result = {}
        entry = coordinator.config_entry
        for webcam in (webcam_result or {}).get("webcams", []):
            if not isinstance(webcam, dict):
                continue
            webcams.append(
                {
                    "name": webcam.get("name"),
                    "stream_url": _webcam_url(entry, webcam.get("stream_url")),
                    "snapshot_url": _webcam_url(entry, webcam.get("snapshot_url")),
                }
            )

        power = data.get("power_devices") or {}
        power_devices = [
            {
                "device": device.get("device"),
                "status": device.get("status"),
                "locked_while_printing": device.get("locked_while_printing"),
            }
            for device in power.get("devices", [])
            if isinstance(device, dict) and device.get("device")
        ]

        macros = sorted(
            obj.partition(" ")[2]
            for obj in status
            if obj.startswith("gcode_macro ")
        )
        try:
            system_info_response = await coordinator.async_get_system_info()
        except UpdateFailed:
            system_info_response = {}
        raw_system_info = (
            system_info_response.get("system_info")
            if isinstance(system_info_response, dict)
            else {}
        ) or {}
        if not isinstance(raw_system_info, dict):
            raw_system_info = {}
        raw_cpu_info = raw_system_info.get("cpu_info") or {}
        if not isinstance(raw_cpu_info, dict):
            raw_cpu_info = {}
        safe_cpu_keys = (
            "cpu_count",
            "bits",
            "processor",
            "cpu_desc",
            "hardware_desc",
            "model",
            "total_memory",
            "memory_units",
        )
        system_info = {
            "provider": raw_system_info.get("provider"),
            "cpu_info": {
                key: raw_cpu_info[key] for key in safe_cpu_keys if key in raw_cpu_info
            },
        }
        try:
            raw_server_info = await coordinator.async_get_server_info()
        except UpdateFailed:
            raw_server_info = {}
        if not isinstance(raw_server_info, dict):
            raw_server_info = {}
        server_info = {
            key: raw_server_info[key]
            for key in ("moonraker_version", "api_version", "components", "failed_components", "warnings")
            if key in raw_server_info
        }
        entry_options = coordinator.config_entry.options
        tracked_objects = [
            {
                "name": object_name,
                "fields": None if fields is None else sorted(fields),
            }
            for object_name, fields in coordinator.query_obj.get("objects", {}).items()
        ]

        return self.json(
            {
                "entry_id": coordinator.config_entry.entry_id,
                "printer": coordinator.api_device_name,
                "available": coordinator.last_update_success,
                "selected_file": coordinator.selected_file,
                "status": status,
                "printer_info": data.get("printer.info") or {},
                "server_info": server_info,
                "system_info": system_info,
                "meta": {key: data.get(key) for key in _META_KEYS},
                "history": data.get("history") or {},
                "queue": data.get("queue") or {},
                "spoolman": data.get("spoolman") or {},
                "machine_update": data.get("machine_update") or {},
                "power_devices": power_devices,
                "macros": macros,
                "webcams": webcams,
                "gcode_responses": list(coordinator.gcode_responses)[-80:],
                "files": [
                    {
                        "path": file.get("path"),
                        "size": file.get("size"),
                        "modified": file.get("modified"),
                    }
                    for file in files
                    if isinstance(file, dict) and file.get("path")
                ],
                "entries": [
                    {"id": entry_id, "name": other.api_device_name}
                    for entry_id, other in self._coordinators().items()
                ],
                "api_key_configured": bool(entry.data.get(CONF_API_KEY)),
                "settings": {
                    "host": entry.data.get(CONF_URL),
                    "port": _entry_port(entry),
                    "tls": bool(entry.data.get(CONF_TLS, False)),
                    "idle_poll_seconds": coordinator.polling_interval.total_seconds(),
                    "print_poll_seconds": PRINTING_POLLING_RATE,
                    "quiet_unreachable": bool(
                        entry_options.get(CONF_OPTION_QUIET_UNREACHABLE, False)
                    ),
                },
                "platforms": [
                    getattr(platform, "value", str(platform))
                    for platform in coordinator.platforms
                ],
                "tracked_objects": tracked_objects,
                "available_objects": (coordinator._printer_objects_list or {}).get(
                    "objects", []
                ),
                "integration_version": VERSION,
            }
        )


def _relative_gcode_path(filename: str | None) -> str | None:
    """Normalize a Moonraker gcode path and reject path traversal."""
    if not filename:
        return None
    normalized = filename.replace("\\", "/").strip()
    was_absolute = normalized.startswith("/")
    normalized = normalized.lstrip("/")
    lowered = normalized.casefold()
    if lowered.startswith(f"{_GCODE_ROOT}/"):
        normalized = normalized[len(_GCODE_ROOT) + 1 :]
    elif was_absolute:
        marker = f"/{_GCODE_ROOT}/"
        index = lowered.find(marker)
        if index >= 0:
            normalized = normalized[index + len(marker):]
    if not normalized or any(part in ("", ".", "..") for part in normalized.split("/")):
        return None
    return normalized


class MoonrakerPanelGcodeView(_PanelViewBase):
    """Stream the active gcode file to the authenticated dashboard for preview."""

    url = PANEL_GCODE_URL
    name = "api:moonraker:panel_gcode"

    async def get(self, request):
        """Proxy the active gcode file without exposing Moonraker credentials."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return self.json({"error": "unknown printer"}, status_code=404)

        status = (coordinator.data or {}).get("status") or {}
        print_stats = status.get("print_stats") or {}
        virtual_sdcard = status.get("virtual_sdcard") or {}
        active_path = _relative_gcode_path(
            print_stats.get("filename") or virtual_sdcard.get("file_path")
        )
        requested_path = _relative_gcode_path(request.query.get("filename"))
        if not requested_path or requested_path != active_path:
            return self.json({"error": "only the active gcode file can be previewed"}, status_code=404)

        file_list = (coordinator.data or {}).get("file_list") or {}
        files = file_list.get("files") if isinstance(file_list, dict) else file_list
        allowed_paths = {
            _relative_gcode_path(file.get("path"))
            for file in files or []
            if isinstance(file, dict)
        }
        if requested_path not in allowed_paths:
            return self.json({"error": "gcode file is not in the printer file list"}, status_code=404)

        entry = coordinator.config_entry
        scheme = "https" if entry.data.get(CONF_TLS, False) else "http"
        url = (
            f"{scheme}://{entry.data.get(CONF_URL)}:{_entry_port(entry)}"
            f"/server/files/{_GCODE_ROOT}/{quote(requested_path, safe='/')}"
        )
        api_key = entry.data.get(CONF_API_KEY)
        headers = {"X-Api-Key": api_key} if api_key else {}
        session = async_get_clientsession(self.hass, verify_ssl=False)
        response = None
        response_started = False
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=TIMEOUT, sock_read=30)
        try:
            async with session.get(url, headers=headers, timeout=timeout) as upstream:
                if upstream.status != 200:
                    return web.Response(status=404)
                if upstream.content_length and upstream.content_length > _MAX_TOOLPATH_BYTES:
                    return self.json(
                        {"error": "gcode file exceeds the interactive preview limit"},
                        status_code=413,
                    )
                response_headers = {
                    "Content-Type": "text/plain; charset=utf-8",
                    "Cache-Control": "no-store",
                }
                if upstream.content_length is not None:
                    response_headers["Content-Length"] = str(upstream.content_length)
                response = web.StreamResponse(headers=response_headers)
                await response.prepare(request)
                response_started = True
                bytes_streamed = 0
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    bytes_streamed += len(chunk)
                    if bytes_streamed > _MAX_TOOLPATH_BYTES:
                        response.force_close()
                        return response
                    await response.write(chunk)
                await response.write_eof()
                return response
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as exception:
            _LOGGER.debug("Could not stream active gcode to the dashboard: %s", exception)
            if response_started and response is not None:
                response.force_close()
                return response
            return web.Response(status=502)


class MoonrakerPanelThumbnailView(_PanelViewBase):
    """Proxy the current job's thumbnail from Moonraker."""

    url = PANEL_THUMB_URL
    name = "api:moonraker:panel_thumbnail"

    async def get(self, request):
        """Return the thumbnail image for the active job."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return web.Response(status=404)

        thumbnail_path = (coordinator.data or {}).get("thumbnails_path")
        if not thumbnail_path:
            return web.Response(status=404)

        entry = coordinator.config_entry
        scheme = "https" if entry.data.get(CONF_TLS, False) else "http"
        url = (
            f"{scheme}://{entry.data.get(CONF_URL)}:{_entry_port(entry)}"
            f"/server/files/{_GCODE_ROOT}/{quote(thumbnail_path, safe='/')}"
        )
        api_key = entry.data.get(CONF_API_KEY)
        headers = {"X-Api-Key": api_key} if api_key else {}
        session = async_get_clientsession(self.hass, verify_ssl=False)
        try:
            async with (
                async_timeout.timeout(TIMEOUT),
                session.get(url, headers=headers) as response,
            ):
                if response.status != 200:
                    return web.Response(status=404)
                body = await response.read()
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as exception:
            _LOGGER.debug("Could not fetch thumbnail from Moonraker: %s", exception)
            return web.Response(status=502)
        return web.Response(body=body, content_type=response.content_type)


class MoonrakerPanelActionView(_PanelViewBase):
    """Execute panel control actions against the printer."""

    url = PANEL_ACTION_URL
    name = "api:moonraker:panel_action"

    async def post(self, request):
        """Handle a JSON action payload."""
        try:
            payload: dict[str, Any] = await request.json()
        except (ValueError, TypeError):
            return self.json({"error": "invalid json"}, status_code=400)

        coordinator = self._resolve(payload.get("entry_id"))
        if coordinator is None:
            return self.json({"error": "unknown printer"}, status_code=404)

        action = str(payload.get("action") or "")
        try:
            error = await self._run_action(coordinator, action, payload)
        except Exception as exception:  # noqa: BLE001 - surfaced to the UI
            _LOGGER.debug("Moonraker panel action %s failed", action, exc_info=True)
            return self.json({"error": str(exception)}, status_code=502)
        if error:
            return self.json({"error": error}, status_code=400)
        return self.json({"ok": True})

    async def _run_action(self, coordinator, action: str, payload) -> str | None:
        """Execute a panel action; return an error string or None."""
        if action in _DIRECT_ACTIONS:
            await coordinator.async_send_data(_DIRECT_ACTIONS[action])
            return None

        if action == "jog":
            axis = str(payload.get("axis") or "").upper()
            try:
                distance = float(payload.get("dist"))
            except (TypeError, ValueError):
                return "numeric distance required"
            if axis not in ("X", "Y", "Z"):
                return "axis must be X, Y, or Z"
            feed = 600 if axis == "Z" else 6000
            await coordinator.async_send_data(
                METHODS.PRINTER_GCODE_SCRIPT,
                {"script": f"G91\nG1 {axis}{distance} F{feed}\nG90"},
            )
            return None

        if action == "preheat":
            preset = str(payload.get("preset") or "").lower()
            temps = _PREHEAT_PRESETS.get(preset)
            if temps is None:
                return "unknown preset"
            await coordinator.async_send_data(
                METHODS.PRINTER_GCODE_SCRIPT,
                {"script": f"M104 S{temps[0]}\nM140 S{temps[1]}"},
            )
            return None

        if action in ("run_gcode", "run_macro"):
            script = str(payload.get("script") or "").strip()
            if not script:
                return "script required"
            await coordinator.async_send_data(
                METHODS.PRINTER_GCODE_SCRIPT, {"script": script}
            )
            return None

        if action in ("select_file", "print_file", "enqueue_file"):
            filename = str(payload.get("filename") or "").strip() or (
                coordinator.selected_file or ""
            )
            if not filename:
                return "no file selected"
            if action == "select_file":
                coordinator.selected_file = filename
            elif action == "print_file":
                coordinator.selected_file = filename
                await coordinator.async_send_data(
                    METHODS.PRINTER_PRINT_START, {"filename": filename}
                )
            else:
                await coordinator.async_send_data(
                    METHODS.SERVER_JOB_QUEUE_POST_JOB,
                    {"filenames": [filename]},
                )
            return None

        if action == "delete_file":
            filename = str(payload.get("filename") or "").strip()
            if not filename:
                return "filename required"
            await coordinator.async_send_data(
                METHODS.SERVER_FILES_DELETE_FILE, {"path": filename}
            )
            await coordinator.async_refresh_files()
            return None

        if action == "power":
            device = str(payload.get("device") or "").strip()
            power_action = str(payload.get("power_action") or "").lower()
            if not device or power_action not in ("on", "off"):
                return "device and power_action=on|off required"
            await coordinator.async_send_data(
                METHODS.MACHINE_DEVICE_POWER_POST_DEVICE,
                {"device": device, "action": power_action},
            )
            return None

        if action == "refresh_files":
            await coordinator.async_refresh_files()
            return None

        if action in _GCODE_ACTIONS:
            template = _GCODE_ACTIONS[action]
            if "{}" in template:
                try:
                    value = float(payload.get("value"))
                except (TypeError, ValueError):
                    return "numeric value required"
                script = template.format(value)
            else:
                script = template
            await coordinator.async_send_data(
                METHODS.PRINTER_GCODE_SCRIPT, {"script": script}
            )
            return None

        return "unknown action"


async def register_panel_views(hass: HomeAssistant) -> None:
    """Register panel HTTP views and the authenticated HA sidebar panel."""
    from homeassistant.components.panel_custom import async_register_panel

    hass.http.register_view(MoonrakerPanelView())
    hass.http.register_view(MoonrakerPanelEmbedView(hass))
    hass.http.register_view(MoonrakerPanelModuleView(hass))
    hass.http.register_view(MoonrakerPanelClientView(hass))
    hass.http.register_view(MoonrakerUploadRedirectView())
    hass.http.register_view(MoonrakerPanelDataView(hass))
    hass.http.register_view(MoonrakerPanelGcodeView(hass))
    hass.http.register_view(MoonrakerPanelThumbnailView(hass))
    hass.http.register_view(MoonrakerPanelActionView(hass))
    await async_register_panel(
        hass,
        frontend_url_path=PANEL_FRONTEND_PATH,
        webcomponent_name="moonraker-control-panel",
        sidebar_title="Moonraker Control",
        sidebar_icon="mdi:printer-3d",
        module_url=PANEL_MODULE_URL,
        embed_iframe=False,
        config={"frame_url": PANEL_EMBED_URL},
    )
