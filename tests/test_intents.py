"""Tests for the Assist intent handlers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers import intent

from custom_components.moonraker.const import DOMAIN, METHODS
from custom_components.moonraker.intents import async_register_intents


def _coordinator(name="Voron", state="printing", **extra):
    """Build a minimal coordinator double."""
    status = {
        "print_stats": {
            "state": state,
            "filename": "job.gcode",
            "print_duration": 600.0,
            "total_duration": 3600.0,
        },
        "display_status": {"progress": 0.4},
    }
    return SimpleNamespace(
        api_device_name=name,
        data={"status": status},
        async_send_data=AsyncMock(),
        **extra,
    )


def _speech(response) -> str:
    """Extract the speech text from an intent response."""
    return response.speech["plain"]["speech"]


async def test_status_intent_single_printer(hass):
    """A status query with one printer answers without a name slot."""
    hass.data.setdefault(DOMAIN, {})["a"] = _coordinator()
    async_register_intents(hass)
    response = await intent.async_handle(hass, "test", "MoonrakerPrintStatus", {}, None)
    speech = _speech(response)
    assert "Voron is printing" in speech
    assert "job.gcode" in speech
    assert "40 percent" in speech
    assert "50 minutes" in speech


async def test_status_intent_named_and_unknown(hass):
    """Named slots resolve printers; unknown names list the fleet."""
    hass.data.setdefault(DOMAIN, {})["a"] = _coordinator("Voron")
    hass.data[DOMAIN]["b"] = _coordinator("Ender", state="standby")
    async_register_intents(hass)

    response = await intent.async_handle(hass, "test", "MoonrakerPrintStatus", {}, None)
    assert "which printer" in _speech(response)

    response = await intent.async_handle(
        hass,
        "test",
        "MoonrakerPrintStatus",
        {"name": {"value": "ender"}},
        None,
    )
    assert _speech(response) == "Ender is standby."

    response = await intent.async_handle(
        hass,
        "test",
        "MoonrakerPrintStatus",
        {"name": {"value": "prusa"}},
        None,
    )
    speech = _speech(response)
    assert "no printer named prusa" in speech
    assert "Voron" in speech and "Ender" in speech


async def test_status_intent_no_printers(hass):
    """No configured printers produce a clear message."""
    hass.data.setdefault(DOMAIN, {})
    async_register_intents(hass)
    response = await intent.async_handle(hass, "test", "MoonrakerPrintStatus", {}, None)
    assert "no Moonraker printers" in _speech(response)


async def test_pause_and_resume_intents(hass):
    """Pause/resume send the printer command and speak the outcome."""
    coordinator = _coordinator()
    hass.data.setdefault(DOMAIN, {})["a"] = coordinator
    async_register_intents(hass)

    response = await intent.async_handle(hass, "test", "MoonrakerPrintPause", {}, None)
    coordinator.async_send_data.assert_awaited_once_with(METHODS.PRINTER_PRINT_PAUSE)
    assert _speech(response) == "Pausing Voron."

    coordinator.data["status"]["print_stats"]["state"] = "paused"
    response = await intent.async_handle(hass, "test", "MoonrakerPrintResume", {}, None)
    coordinator.async_send_data.assert_awaited_with(METHODS.PRINTER_PRINT_RESUME)
    assert _speech(response) == "Resuming Voron."


async def test_control_intent_idle_and_unreachable(hass):
    """Idle printers report state; failures speak a reachability error."""
    coordinator = _coordinator(state="standby")
    hass.data.setdefault(DOMAIN, {})["a"] = coordinator
    async_register_intents(hass)

    response = await intent.async_handle(hass, "test", "MoonrakerPrintPause", {}, None)
    assert _speech(response) == "Voron is standby."

    coordinator.async_send_data.side_effect = RuntimeError("down")
    response = await intent.async_handle(hass, "test", "MoonrakerPrintPause", {}, None)
    assert "could not reach Voron" in _speech(response)


async def test_control_intent_no_printers(hass):
    """Control intents without printers explain there is nothing to use."""
    hass.data.setdefault(DOMAIN, {})
    async_register_intents(hass)
    response = await intent.async_handle(hass, "test", "MoonrakerPrintPause", {}, None)
    assert "no Moonraker printers" in _speech(response)
