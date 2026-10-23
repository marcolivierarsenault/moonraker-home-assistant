"""Live control panel views for the Moonraker integration."""

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import aiohttp
import async_timeout
import voluptuous as vol
from aiohttp import web

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_OPTION_PANEL_ROLE,
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
from .analyzer import CHAMBER_WARM_MIN_C, HIGH_SHRINK_MATERIALS, _finite_number
from .sensor import calculate_current_layer, calculate_total_layer

if TYPE_CHECKING:
    from . import MoonrakerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "/api/moonraker/panel"
PANEL_EMBED_URL = "/api/moonraker/panel_embed"
PANEL_MODULE_URL = "/api/moonraker/panel_module.js"
PANEL_CLIENT_URL = "/api/moonraker/panel_client.js"
PANEL_I18N_URL = "/api/moonraker/panel_i18n.js"
PANEL_PARSE_URL = "/api/moonraker/toolpath_parse.js"
PANEL_WORKER_URL = "/api/moonraker/toolpath_worker.js"
PANEL_DATA_URL = "/api/moonraker/panel_data"
PANEL_GCODE_URL = "/api/moonraker/panel_gcode"
PANEL_THUMB_URL = "/api/moonraker/panel_thumbnail"
PANEL_SNAPSHOT_URL = "/api/moonraker/panel_webcam_snapshot"
PANEL_ACTION_URL = "/api/moonraker/panel_action"
PANEL_FILE_META_URL = "/api/moonraker/panel_file_meta"
PANEL_MANIFEST_URL = "/api/moonraker/panel_manifest.json"
PANEL_SW_URL = "/api/moonraker/panel_sw.js"
PANEL_FRONTEND_PATH = "moonraker-control-deck"
UPLOAD_URL = "/api/moonraker/gcode_upload"

_GCODE_ROOT = "gcodes"
_MAX_TOOLPATH_BYTES = 128 * 1024 * 1024
_AUX_CACHE_TTL = 40 / 3
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "panel.html")
_MODULE_PATH = os.path.join(os.path.dirname(__file__), "panel_module.js")
_CLIENT_PATH = os.path.join(os.path.dirname(__file__), "panel_client.js")
_I18N_PATH = os.path.join(os.path.dirname(__file__), "panel_i18n.js")
_PARSE_PATH = os.path.join(os.path.dirname(__file__), "toolpath_parse.js")
_WORKER_PATH = os.path.join(os.path.dirname(__file__), "toolpath_worker.js")

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
    "probe_mesh": "BED_MESH_CALIBRATE",
    "home_x": "G28 X",
    "home_y": "G28 Y",
    "home_z": "G28 Z",
    "home_all": "G28",
}

_QUEUE_ACTIONS = {"pause_queue", "delete_queue_job", "jump_queue_job"}

# Actions a non-admin "operator" may run when the entry's panel_role
# option allows it. Live-print adjustments only — no G-code scripts,
# file management, power, restarts, or queue changes.
_OPERATOR_ACTIONS = {
    "pause",
    "resume",
    "set_speed",
    "set_flow",
    "set_fan",
    "set_extruder",
    "set_bed",
    "z_adjust",
    "cooldown",
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


def _coordinators(hass: HomeAssistant) -> dict[str, "MoonrakerDataUpdateCoordinator"]:
    """Return all configured Moonraker coordinators by entry id."""
    from . import MoonrakerDataUpdateCoordinator

    return {
        entry_id: coordinator
        for entry_id, coordinator in hass.data.get(DOMAIN, {}).items()
        if isinstance(coordinator, MoonrakerDataUpdateCoordinator)
    }


def _resolve_coordinator(hass: HomeAssistant, entry_id: str | None):
    """Resolve a coordinator by entry id, or the first configured one."""
    coordinators = _coordinators(hass)
    if entry_id:
        return coordinators.get(entry_id)
    return next(iter(coordinators.values()), None)


async def _panel_aux_data(coordinator) -> dict[str, Any]:
    """Fetch slowly-changing Moonraker datasets the coordinator does not track.

    The results are cached briefly so websocket pushes do not fan out into a
    burst of extra Moonraker calls on every coordinator update.
    """
    lock = getattr(coordinator, "_panel_aux_lock", None)
    if lock is None:
        lock = coordinator._panel_aux_lock = asyncio.Lock()
    async with lock:
        cache = getattr(coordinator, "_panel_aux_cache", None)
        now = time.monotonic()
        if cache is not None and now - cache[0] < _AUX_CACHE_TTL:
            return cache[1]

        async def _fetch(method: METHODS, params=None):
            try:
                return await coordinator.async_fetch_data(method, params, quiet=True)
            except UpdateFailed:
                return None
            except Exception:  # noqa: BLE001 - aux data must never break the panel
                _LOGGER.debug("Panel aux fetch failed for %s", method, exc_info=True)
                return None

        keys = (
            "power_devices",
            "queue",
            "history",
            "machine_update",
            "spoolman",
            "gcode_store",
        )
        results = await asyncio.gather(
            _fetch(METHODS.MACHINE_DEVICE_POWER_DEVICES),
            _fetch(METHODS.SERVER_JOB_QUEUE_STATUS),
            _fetch(METHODS.SERVER_HISTORY_TOTALS),
            _fetch(METHODS.MACHINE_UPDATE_STATUS),
            _fetch(METHODS.SERVER_SPOOLMAN_ID),
            _fetch(METHODS.SERVER_GCODE_STORE, {"count": 200}),
        )
        aux = {
            key: result
            for key, result in zip(keys, results, strict=True)
            if isinstance(result, dict)
        }
        spool_id = (aux.get("spoolman") or {}).get("spool_id")
        if spool_id is not None:
            details = await _fetch(
                METHODS.SERVER_SPOOLMAN_PROXY,
                {
                    "request_method": "GET",
                    "path": f"/api/v1/spool/{spool_id}",
                },
            )
            if isinstance(details, dict):
                aux["spool_details"] = details
        coordinator._panel_aux_cache = (time.monotonic(), aux)
        return aux


def _console_lines(coordinator, gcode_store) -> list[str]:
    """Merge Moonraker's gcode store with live responses for the console."""
    entries = gcode_store.get("gcode_store") if isinstance(gcode_store, dict) else None
    lines = [
        entry["message"]
        for entry in entries or []
        if isinstance(entry, dict) and isinstance(entry.get("message"), str)
    ]
    live = list(coordinator.gcode_responses)
    # Live responses may duplicate the store tail; skip the overlap.
    window = lines[-len(live) :] if live else []
    for line in live:
        if line in window:
            window.remove(line)
        else:
            lines.append(line)
    return lines[-300:]


def _fleet_summary(coordinator) -> dict[str, Any]:
    """Summarize a coordinator's cached state for the fleet strip."""
    data = coordinator.data or {}
    status = data.get("status") or {}
    print_stats = status.get("print_stats") or {}
    display = status.get("display_status") or {}
    virtual = status.get("virtual_sdcard") or {}
    progress = display.get("progress")
    if not isinstance(progress, int | float):
        progress = virtual.get("progress")
    if not isinstance(progress, int | float):
        progress = None
    metrics = coordinator.analyzer.metrics
    return {
        "id": coordinator.config_entry.entry_id,
        "name": coordinator.api_device_name,
        "available": coordinator.last_update_success,
        "state": print_stats.get("state"),
        "progress": progress,
        "hotend": (status.get("extruder") or {}).get("temperature"),
        "bed": (status.get("heater_bed") or {}).get("temperature"),
        "filename": print_stats.get("filename"),
        "material": metrics.get("spool_material"),
        "ambient_c": metrics.get("ambient_c"),
        "oee": {
            "utilization_pct": metrics.get("oee_utilization_pct"),
            "success_rate_pct": metrics.get("oee_success_rate_pct"),
            "throughput_gh": metrics.get("oee_throughput_gh"),
        },
    }


def _route_needs(coordinator) -> dict[str, Any]:
    """Summarize the requesting printer's next queued job for routing."""
    data = coordinator.data or {}
    jobs = (data.get("queue") or {}).get("queued_jobs")
    if not isinstance(jobs, list):
        return {}
    meta = data.get("queue_meta") or {}
    for job in jobs:
        if not isinstance(job, dict) or not job.get("filename"):
            continue
        job_meta = meta.get(str(job.get("filename")))
        job_meta = job_meta if isinstance(job_meta, dict) else {}
        return {
            "filename": job.get("filename"),
            "filament_mm": job_meta.get("filament_total"),
            "material": job_meta.get("filament_type"),
        }
    return {}


def _route_score(coordinator, needs: dict[str, Any]) -> dict[str, Any]:
    """Score how fit a fleet printer is for the next queued job."""
    if not coordinator.last_update_success:
        return {"score": 0, "reasons": ["offline"]}
    status = (coordinator.data or {}).get("status") or {}
    state = (status.get("print_stats") or {}).get("state")
    metrics = coordinator.analyzer.metrics
    score = 0
    reasons: list[str] = []
    if state in (None, "standby", "complete", "cancelled", "error"):
        score += 40
    else:
        reasons.append(f"busy ({state})")
    loaded = str(metrics.get("spool_material") or "").upper()
    wanted = str(needs.get("material") or "").upper()
    if not wanted or not loaded or wanted in loaded or loaded in wanted:
        score += 20
    else:
        reasons.append(f"loaded {loaded or 'unknown'}")
    remaining_mm = _finite_number(metrics.get("spool_remaining_mm"))
    needed_mm = _finite_number(needs.get("filament_mm"))
    if needed_mm is None or remaining_mm is None or remaining_mm >= needed_mm:
        score += 20
    else:
        reasons.append("insufficient filament")
    preflight = metrics.get("preflight") or {}
    if preflight.get("mesh_fresh") is not False:
        score += 10
    else:
        reasons.append("stale mesh")
    ambient = _finite_number(metrics.get("ambient_c"))
    if (
        ambient is None
        or ambient >= CHAMBER_WARM_MIN_C
        or not any(token in loaded for token in HIGH_SHRINK_MATERIALS)
    ):
        score += 10
    else:
        reasons.append("cold chamber")
    return {"score": score, "reasons": reasons}


def _spool_details(spool) -> dict[str, Any]:
    """Whitelist display-safe fields from a Spoolman spool record."""
    if not isinstance(spool, dict):
        return {}
    filament = spool.get("filament")
    filament = filament if isinstance(filament, dict) else {}
    details = {
        key: spool[key]
        for key in (
            "id",
            "remaining_weight",
            "used_weight",
            "remaining_length",
            "used_length",
        )
        if key in spool
    }
    details["filament"] = {
        key: filament[key]
        for key in ("name", "material", "vendor", "diameter", "density", "color_hex")
        if key in filament
    }
    return details


def _bed_bounds(settings_response) -> dict[str, dict[str, float]]:
    """Extract axis travel limits from the cached configfile settings."""
    status = (settings_response or {}).get("status")
    if not isinstance(status, dict):
        status = {}
    configfile = status.get("configfile")
    if not isinstance(configfile, dict):
        configfile = {}
    config = configfile.get("settings")
    if not isinstance(config, dict):
        config = {}
    bounds = {}
    for axis in ("x", "y", "z"):
        section = config.get(f"stepper_{axis}")
        if not isinstance(section, dict):
            continue
        axis_bounds = {
            name: section[key]
            for name, key in (("min", "position_min"), ("max", "position_max"))
            if isinstance(section.get(key), int | float)
        }
        if axis_bounds:
            bounds[axis] = axis_bounds
    return bounds


def _layer_info(data: dict[str, Any]) -> dict[str, int]:
    """Return computed layer counters for the panel."""
    merged = dict(data)
    merged.setdefault("status", {})
    return {
        "current": calculate_current_layer(merged),
        "total": calculate_total_layer(merged),
    }


async def _panel_payload(hass: HomeAssistant, coordinator) -> dict[str, Any]:
    """Assemble the panel data payload for a coordinator."""
    data = coordinator.data or {}
    aux = await _panel_aux_data(coordinator)
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

    power = aux.get("power_devices") or {}
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
        obj.partition(" ")[2] for obj in status if obj.startswith("gcode_macro ")
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
        for key in (
            "moonraker_version",
            "api_version",
            "components",
            "failed_components",
            "warnings",
        )
        if key in raw_server_info
    }
    try:
        config_settings_response = await coordinator.async_get_config_settings()
    except UpdateFailed:
        config_settings_response = {}
    except Exception:  # noqa: BLE001 - axis limits are optional for the panel
        config_settings_response = {}
    entry_options = coordinator.config_entry.options
    tracked_objects = [
        {
            "name": object_name,
            "fields": None if fields is None else sorted(fields),
        }
        for object_name, fields in coordinator.query_obj.get("objects", {}).items()
    ]

    return {
        "entry_id": coordinator.config_entry.entry_id,
        "printer": coordinator.api_device_name,
        "available": coordinator.last_update_success,
        "generated_at": time.time(),
        "selected_file": coordinator.selected_file,
        "status": status,
        "printer_info": data.get("printer.info") or {},
        "server_info": server_info,
        "system_info": system_info,
        "meta": {key: data.get(key) for key in _META_KEYS},
        "history": aux.get("history") or {},
        "queue": aux.get("queue") or {},
        "spoolman": aux.get("spoolman") or {},
        "spool_details": _spool_details(aux.get("spool_details")),
        "machine_update": aux.get("machine_update") or {},
        "bed_bounds": _bed_bounds(config_settings_response),
        "layers": _layer_info(data),
        "power_devices": power_devices,
        "macros": macros,
        "webcams": webcams,
        "gcode_responses": _console_lines(coordinator, aux.get("gcode_store")),
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
            for entry_id, other in _coordinators(hass).items()
        ],
        "fleet": [_fleet_summary(other) for other in _coordinators(hass).values()],
        "router": {
            "needs": _route_needs(coordinator),
            "scores": {
                entry_id: _route_score(other, _route_needs(coordinator))
                for entry_id, other in _coordinators(hass).items()
            },
        },
        "analysis": coordinator.analyzer.as_dict(),
        "api_key_configured": bool(entry.data.get(CONF_API_KEY)),
        "settings": {
            "host": entry.data.get(CONF_URL),
            "port": _entry_port(entry),
            "tls": bool(entry.data.get(CONF_TLS, False)),
            "idle_poll_seconds": coordinator.polling_interval.total_seconds(),
            "print_poll_seconds": round(PRINTING_POLLING_RATE, 1),
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


class _PanelViewBase(HomeAssistantView):
    """Shared helpers for panel views."""

    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        self.hass = hass

    def _coordinators(self) -> dict[str, "MoonrakerDataUpdateCoordinator"]:
        return _coordinators(self.hass)

    def _resolve(self, entry_id: str | None):
        return _resolve_coordinator(self.hass, entry_id)


class MoonrakerPanelView(HomeAssistantView):
    """Redirect the legacy panel URL to the authenticated HA sidebar panel."""

    url = PANEL_URL
    name = "api:moonraker:panel"
    requires_auth = False

    async def get(self, request):
        """Redirect to the Home Assistant frontend panel."""
        return web.Response(status=302, headers={"Location": f"/{PANEL_FRONTEND_PATH}"})


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


class MoonrakerPanelI18nView(_PanelAssetView):
    """Serve the panel's translation tables."""

    url = PANEL_I18N_URL
    name = "api:moonraker:panel_i18n"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        super().__init__(hass, _I18N_PATH)


class MoonrakerPanelParseView(_PanelAssetView):
    """Serve the shared toolpath parser core."""

    url = PANEL_PARSE_URL
    name = "api:moonraker:toolpath_parse"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        super().__init__(hass, _PARSE_PATH)


class MoonrakerPanelWorkerView(_PanelAssetView):
    """Serve the toolpath parsing web worker."""

    url = PANEL_WORKER_URL
    name = "api:moonraker:toolpath_worker"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        super().__init__(hass, _WORKER_PATH)


class MoonrakerPanelManifestView(HomeAssistantView):
    """Serve the web app manifest so the panel can install as a PWA."""

    url = PANEL_MANIFEST_URL
    name = "api:moonraker:panel_manifest"
    requires_auth = False

    async def get(self, request):
        """Return the install manifest for the control deck."""
        return web.json_response(
            {
                "name": "Moonraker Control Deck",
                "short_name": "Moonraker",
                "start_url": PANEL_EMBED_URL,
                "scope": "/api/moonraker/",
                "display": "standalone",
                "background_color": "#050a08",
                "theme_color": "#050a08",
                "icons": [
                    {
                        "src": "/static/icons/favicon-192x192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                    },
                    {
                        "src": "/static/icons/favicon-512x512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                    },
                ],
            }
        )


_PANEL_SW_SOURCE = """/* Moonraker control deck service worker: installability + asset cache. */
const SW_CACHE = "moonraker-deck-v1";
const ASSETS = [
  "/api/moonraker/panel_client.js",
  "/api/moonraker/panel_i18n.js",
  "/api/moonraker/toolpath_parse.js",
  "/api/moonraker/toolpath_worker.js",
];
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SW_CACHE).then((cache) => cache.addAll(ASSETS)).catch(() => {}),
  );
  self.skipWaiting();
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== SW_CACHE).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || !ASSETS.includes(url.pathname)) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const clone = response.clone();
        caches.open(SW_CACHE).then((cache) => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});
"""


class MoonrakerPanelServiceWorkerView(HomeAssistantView):
    """Serve a minimal service worker so the panel can install as a PWA."""

    url = PANEL_SW_URL
    name = "api:moonraker:panel_sw"
    requires_auth = False

    async def get(self, request):
        """Return the service worker source."""
        return web.Response(
            text=_PANEL_SW_SOURCE,
            content_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )


class MoonrakerUploadRedirectView(HomeAssistantView):
    """Redirect browser navigation to the upload UI in the control panel."""

    url = UPLOAD_URL
    name = "api:moonraker:gcode_upload_page"
    requires_auth = False

    async def get(self, request):
        """Redirect to the authenticated Home Assistant panel."""
        return web.Response(status=302, headers={"Location": f"/{PANEL_FRONTEND_PATH}"})


class MoonrakerPanelDataView(_PanelViewBase):
    """Return a JSON snapshot of coordinator data for the panel."""

    url = PANEL_DATA_URL
    name = "api:moonraker:panel_data"

    async def get(self, request):
        """Return the current coordinator data snapshot."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return self.json({"error": "no printer configured"}, status_code=404)
        return self.json(await _panel_payload(self.hass, coordinator))


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
            normalized = normalized[index + len(marker) :]
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
            return self.json(
                {"error": "only the active gcode file can be previewed"},
                status_code=404,
            )

        file_list = (coordinator.data or {}).get("file_list") or {}
        files = file_list.get("files") if isinstance(file_list, dict) else file_list
        allowed_paths = {
            _relative_gcode_path(file.get("path"))
            for file in files or []
            if isinstance(file, dict)
        }
        if requested_path not in allowed_paths:
            return self.json(
                {"error": "gcode file is not in the printer file list"}, status_code=404
            )

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
                if (
                    upstream.content_length
                    and upstream.content_length > _MAX_TOOLPATH_BYTES
                ):
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
            _LOGGER.debug(
                "Could not stream active gcode to the dashboard: %s", exception
            )
            if response_started and response is not None:
                response.force_close()
                return response
            return web.Response(status=502)


def _best_thumbnail_relative_path(meta) -> str | None:
    """Pick the largest thumbnail relative path from a metadata response."""
    thumbnails = meta.get("thumbnails") if isinstance(meta, dict) else None
    if not isinstance(thumbnails, list):
        return None
    best_path = None
    best_size = -1.0
    for thumbnail in thumbnails:
        if not isinstance(thumbnail, dict):
            continue
        relative_path = thumbnail.get("relative_path")
        if not relative_path:
            continue
        size = thumbnail.get("size")
        try:
            size_value = float(size) if size is not None else None
        except (TypeError, ValueError):
            size_value = None
        if size_value is None:
            if best_path is None:
                best_path = relative_path
            continue
        if size_value > best_size:
            best_size = size_value
            best_path = relative_path
    return best_path


class MoonrakerPanelFileMetaView(_PanelViewBase):
    """Return slicer metadata for an arbitrary G-code file."""

    url = PANEL_FILE_META_URL
    name = "api:moonraker:panel_file_meta"

    _META_WHITELIST = (
        "estimated_time",
        "filament_total",
        "filament_weight_total",
        "filament_type",
        "filament_name",
        "layer_count",
        "layer_height",
        "first_layer_height",
        "object_height",
        "slicer",
        "slicer_version",
        "nozzle_diameter",
        "first_layer_extr_temp",
        "first_layer_bed_temp",
        "chamber_temp",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "z_min",
        "z_max",
        "size",
        "modified",
    )

    async def get(self, request):
        """Fetch and whitelist metadata for the requested file."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return self.json({"error": "no printer configured"}, status_code=404)
        filename = str(request.query.get("filename") or "").strip()
        if not filename:
            return self.json({"error": "filename required"}, status_code=400)
        from . import _normalize_gcode_path

        normalized, _root = _normalize_gcode_path(filename)
        if not normalized:
            return self.json({"error": "invalid filename"}, status_code=400)
        try:
            meta = await coordinator.async_fetch_data(
                METHODS.SERVER_FILES_METADATA, {"filename": normalized}
            )
        except UpdateFailed:
            return self.json({"error": "metadata unavailable"}, status_code=502)
        if not isinstance(meta, dict):
            meta = {}
        payload = {key: meta[key] for key in self._META_WHITELIST if key in meta}
        payload["has_thumbnail"] = _best_thumbnail_relative_path(meta) is not None
        return self.json(payload)


class MoonrakerPanelThumbnailView(_PanelViewBase):
    """Proxy a G-code thumbnail from Moonraker."""

    url = PANEL_THUMB_URL
    name = "api:moonraker:panel_thumbnail"

    async def get(self, request):
        """Return the thumbnail image for the active job or a named file."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return web.Response(status=404)

        filename = str(request.query.get("filename") or "").strip()
        thumbnail_path = (coordinator.data or {}).get("thumbnails_path")
        if filename:
            from . import _build_thumbnail_path, _normalize_gcode_path

            normalized, root = _normalize_gcode_path(filename)
            thumbnail_path = None
            if normalized:
                try:
                    meta = await coordinator.async_fetch_data(
                        METHODS.SERVER_FILES_METADATA, {"filename": normalized}
                    )
                except UpdateFailed:
                    meta = {}
                best = _best_thumbnail_relative_path(meta)
                if best:
                    thumbnail_path = _build_thumbnail_path(
                        os.path.dirname(normalized), best, root
                    )
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


class MoonrakerPanelSnapshotView(_PanelViewBase):
    """Proxy a webcam snapshot so timelapse frames are same-origin."""

    url = PANEL_SNAPSHOT_URL
    name = "api:moonraker:panel_webcam_snapshot"

    async def get(self, request):
        """Return the latest snapshot for the named webcam."""
        coordinator = self._resolve(request.query.get("printer"))
        if coordinator is None:
            return web.Response(status=404)
        camera_name = str(request.query.get("camera") or "").strip()
        if not camera_name:
            return self.json({"error": "camera required"}, status_code=400)
        try:
            webcam_result = await coordinator.async_get_webcams()
        except Exception:  # noqa: BLE001 - webcams are optional
            return web.Response(status=502)
        entry = coordinator.config_entry
        snapshot_url = None
        for webcam in (webcam_result or {}).get("webcams", []):
            if isinstance(webcam, dict) and webcam.get("name") == camera_name:
                snapshot_url = _webcam_url(entry, webcam.get("snapshot_url"))
                break
        if not snapshot_url:
            return web.Response(status=404)
        session = async_get_clientsession(self.hass, verify_ssl=False)
        api_key = entry.data.get(CONF_API_KEY)
        headers = {"X-Api-Key": api_key} if api_key else {}
        try:
            async with (
                async_timeout.timeout(TIMEOUT),
                session.get(snapshot_url, headers=headers) as response,
            ):
                if response.status != 200:
                    return web.Response(status=404)
                body = await response.read()
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as exception:
            _LOGGER.debug("Could not fetch webcam snapshot: %s", exception)
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
        user = request.get("hass_user")
        if not self._action_permitted(coordinator, action, user):
            return self.json({"error": "unauthorized"}, status_code=403)
        _LOGGER.info(
            "Moonraker panel action %s on %s by %s",
            action,
            coordinator.config_entry.entry_id,
            getattr(user, "name", None) or getattr(user, "id", "unknown"),
        )
        try:
            error = await self._run_action(coordinator, action, payload)
        except Exception as exception:  # noqa: BLE001 - surfaced to the UI
            _LOGGER.debug("Moonraker panel action %s failed", action, exc_info=True)
            return self.json({"error": str(exception)}, status_code=502)
        if error:
            return self.json({"error": error}, status_code=400)
        return self.json({"ok": True})

    @staticmethod
    def _action_permitted(coordinator, action: str, user) -> bool:
        """Admins may run everything; operators only the allowlist."""
        if user is not None and getattr(user, "is_admin", False):
            return True
        role = (coordinator.config_entry.options or {}).get(
            CONF_OPTION_PANEL_ROLE, "admin_only"
        )
        return role == "operator" and action in _OPERATOR_ACTIONS

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

        if action == "apply_queue_plan":
            plan = coordinator.analyzer.metrics.get("queue_plan") or []
            filenames = [item["filename"] for item in plan if item["filename"]]
            if not filenames:
                return "no queue plan available"
            queue = (coordinator.data or {}).get("queue") or {}
            job_ids = [
                str(job.get("job_id"))
                for job in queue.get("queued_jobs") or []
                if isinstance(job, dict) and job.get("job_id")
            ]
            if job_ids:
                await coordinator.async_send_data(
                    METHODS.SERVER_JOB_QUEUE_DELETE_JOB, {"job_ids": job_ids}
                )
            await coordinator.async_send_data(
                METHODS.SERVER_JOB_QUEUE_POST_JOB, {"filenames": filenames}
            )
            return None

        if action in _QUEUE_ACTIONS:
            return await self._run_queue_action(coordinator, action, payload)

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

    async def _run_queue_action(self, coordinator, action: str, payload) -> str | None:
        """Execute a job-queue action; return an error string or None."""
        if action == "pause_queue":
            await coordinator.async_send_data(METHODS.SERVER_JOB_QUEUE_PAUSE)
            return None
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            return "job_id required"
        if action == "delete_queue_job":
            await coordinator.async_send_data(
                METHODS.SERVER_JOB_QUEUE_DELETE_JOB, {"job_ids": [job_id]}
            )
            return None
        await coordinator.async_send_data(
            METHODS.SERVER_JOB_QUEUE_JUMP, {"job_id": job_id}
        )
        return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): "moonraker/panel_subscribe",
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def _ws_panel_subscribe(hass, connection, msg) -> None:
    """Push panel data snapshots whenever the coordinator updates."""
    coordinator = _resolve_coordinator(hass, msg.get("entry_id"))
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "No printer configured")
        return

    async def _push() -> None:
        try:
            payload = await _panel_payload(hass, coordinator)
        except Exception:  # noqa: BLE001 - a bad snapshot must not kill the subscription
            _LOGGER.exception("Failed to assemble Moonraker panel payload")
            return
        connection.send_message(websocket_api.event_message(msg["id"], payload))

    @callback
    def _on_update() -> None:
        hass.async_create_task(_push())

    connection.send_result(msg["id"])
    connection.subscriptions[msg["id"]] = coordinator.async_add_listener(_on_update)
    await _push()


async def register_panel_views(hass: HomeAssistant) -> None:
    """Register panel HTTP views, the websocket feed, and the sidebar panel."""
    from homeassistant.components.panel_custom import async_register_panel

    websocket_api.async_register_command(hass, _ws_panel_subscribe)

    hass.http.register_view(MoonrakerPanelView())
    hass.http.register_view(MoonrakerPanelEmbedView(hass))
    hass.http.register_view(MoonrakerPanelModuleView(hass))
    hass.http.register_view(MoonrakerPanelClientView(hass))
    hass.http.register_view(MoonrakerPanelI18nView(hass))
    hass.http.register_view(MoonrakerPanelParseView(hass))
    hass.http.register_view(MoonrakerPanelWorkerView(hass))
    hass.http.register_view(MoonrakerUploadRedirectView())
    hass.http.register_view(MoonrakerPanelDataView(hass))
    hass.http.register_view(MoonrakerPanelGcodeView(hass))
    hass.http.register_view(MoonrakerPanelThumbnailView(hass))
    hass.http.register_view(MoonrakerPanelSnapshotView(hass))
    hass.http.register_view(MoonrakerPanelFileMetaView(hass))
    hass.http.register_view(MoonrakerPanelActionView(hass))
    hass.http.register_view(MoonrakerPanelManifestView())
    hass.http.register_view(MoonrakerPanelServiceWorkerView())
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
