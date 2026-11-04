"""Diagnostics support for Moonraker."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_URL, DOMAIN

TO_REDACT = {CONF_API_KEY, CONF_URL, "url", "hostname", "api_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "coordinator": {
            "polling_interval": str(coordinator.update_interval),
            "queried_objects": sorted(coordinator.query_obj.get("objects", {}).keys()),
            "status_keys": sorted(
                ((coordinator.data or {}).get("status") or {}).keys()
            ),
            "gcode_responses": list(coordinator.gcode_responses)[-20:],
        },
        "printer_info": async_redact_data(
            (coordinator.data or {}).get("printer.info") or {}, TO_REDACT
        ),
        "analyzer": coordinator.analyzer.as_dict(),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return device diagnostics (delegates to entry diagnostics)."""
    return await async_get_config_entry_diagnostics(hass, entry)
