"""Home Assistant Assist intent handlers for Moonraker printers."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN, METHODS


def _coordinators(hass: HomeAssistant) -> list[Any]:
    """Return all configured Moonraker coordinators."""
    return list(hass.data.get(DOMAIN, {}).values())


def _resolve_printer(hass: HomeAssistant, name: str | None):
    """Find a coordinator by name, or the only configured one."""
    coordinators = _coordinators(hass)
    if not coordinators:
        return None, "no Moonraker printers are configured"
    if not name:
        if len(coordinators) == 1:
            return coordinators[0], None
        return None, "which printer should I use?"
    wanted = name.strip().lower()
    for coordinator in coordinators:
        device_name = str(coordinator.api_device_name or "").lower()
        if device_name == wanted or wanted in device_name:
            return coordinator, None
    known = ", ".join(str(coordinator.api_device_name) for coordinator in coordinators)
    return None, f"no printer named {name}; configured printers: {known}"


def _status_speech(coordinator) -> str:
    """Summarize a coordinator's print state for speech output."""
    status = (coordinator.data or {}).get("status") or {}
    print_stats = status.get("print_stats") or {}
    state = str(print_stats.get("state") or "unknown")
    filename = str(print_stats.get("filename") or "")
    display = status.get("display_status") or {}
    progress = display.get("progress")
    name = coordinator.api_device_name
    if state != "printing":
        return f"{name} is {state}."
    parts = [f"{name} is printing"]
    if filename:
        parts.append(filename)
    if isinstance(progress, int | float):
        parts.append(f"at {round(progress * 100)} percent")
    duration = print_stats.get("print_duration")
    total = print_stats.get("total_duration")
    if (
        isinstance(duration, int | float)
        and isinstance(total, int | float)
        and total > duration
    ):
        remaining = int((total - duration) / 60)
        parts.append(f"with about {remaining} minutes remaining")
    return " ".join(parts) + "."


class MoonrakerPrintStatusIntent(intent.IntentHandler):
    """Report printer state and progress."""

    intent_type = "MoonrakerPrintStatus"
    slot_schema = {vol.Optional("name"): intent.non_empty_string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Speak the current printer status."""
        coordinator, error = _resolve_printer(
            intent_obj.hass,
            (intent_obj.slots.get("name") or {}).get("value"),
        )
        response = intent_obj.create_response()
        if coordinator is None:
            response.async_set_speech(error or "no printer found")
            return response
        response.async_set_speech(_status_speech(coordinator))
        return response


class _PrintControlIntent(intent.IntentHandler):
    """Base for pause/resume voice commands with an explicit action."""

    method: METHODS
    verb: str
    slot_schema = {vol.Optional("name"): intent.non_empty_string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Send the print control command to the resolved printer."""
        coordinator, error = _resolve_printer(
            intent_obj.hass,
            (intent_obj.slots.get("name") or {}).get("value"),
        )
        response = intent_obj.create_response()
        if coordinator is None:
            response.async_set_speech(error or "no printer found")
            return response
        status = (coordinator.data or {}).get("status") or {}
        state = str((status.get("print_stats") or {}).get("state") or "")
        try:
            await coordinator.async_send_data(self.method)
        except Exception:  # noqa: BLE001 - surfaced as a speech error
            response.async_set_speech(
                f"I could not reach {coordinator.api_device_name}"
            )
            return response
        response.async_set_speech(
            f"{self.verb} {coordinator.api_device_name}."
            if state in ("printing", "paused")
            else f"{coordinator.api_device_name} is {state or 'idle'}."
        )
        return response


class MoonrakerPrintPauseIntent(_PrintControlIntent):
    """Pause the active print by voice."""

    intent_type = "MoonrakerPrintPause"
    method = METHODS.PRINTER_PRINT_PAUSE
    verb = "Pausing"


class MoonrakerPrintResumeIntent(_PrintControlIntent):
    """Resume a paused print by voice."""

    intent_type = "MoonrakerPrintResume"
    method = METHODS.PRINTER_PRINT_RESUME
    verb = "Resuming"


def async_register_intents(hass: HomeAssistant) -> None:
    """Register all Moonraker Assist intent handlers (idempotent)."""
    for handler in (
        MoonrakerPrintStatusIntent(),
        MoonrakerPrintPauseIntent(),
        MoonrakerPrintResumeIntent(),
    ):
        intent.async_register(hass, handler)
