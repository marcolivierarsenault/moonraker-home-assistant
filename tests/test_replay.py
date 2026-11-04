"""Replay recorded status streams through the analyzer.

Each ``tests/replay/*.json`` file captures a sequence of status frames
(timestamp + payload delta) like a recorded Moonraker websocket stream.
The harness merges every frame over a shared base status, feeds the
frames through ``MoonrakerAnalyzer.analyze()`` in order, and asserts the
resulting findings, Repairs issues, and history records.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advance_moonraker_control import MoonrakerDataUpdateCoordinator

from .const import MOCK_CONFIG

REPLAY_DIR = Path(__file__).parent / "replay"

BASE_STATUS = {
    "print_stats": {
        "state": "standby",
        "filename": "",
        "print_duration": 0.0,
        "total_duration": 0.0,
        "filament_used": 0.0,
    },
    "extruder": {"temperature": 25.0, "power": 0.0, "target": 0.0},
    "heater_bed": {"temperature": 24.0, "power": 0.0, "target": 0.0},
    "motion_report": {"live_velocity": 0.0, "live_extruder_velocity": 0.0},
}


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.start"),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
        patch(
            "custom_components.advance_moonraker_control._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


def _merge(base: dict, delta: dict) -> dict:
    """Deep-merge a frame delta over the accumulated status."""
    merged = dict(base)
    for key, value in delta.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _scenarios() -> list[dict]:
    """Load every replay scenario."""
    return [json.loads(path.read_text()) for path in sorted(REPLAY_DIR.glob("*.json"))]


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda item: item["name"])
async def test_replay_scenario(hass, scenario):
    """Replay a recorded stream and verify analyzer output."""
    from homeassistant.helpers import issue_registry as ir

    config_entry = MockConfigEntry(
        domain="advance_moonraker_control",
        data=MOCK_CONFIG,
        options=scenario.get("options") or {},
        entry_id=f"replay_{scenario['name']}",
    )
    coordinator = MoonrakerDataUpdateCoordinator(
        hass,
        client=MagicMock(),
        config_entry=config_entry,
        api_device_name="printer",
    )
    analyzer = coordinator.analyzer
    await analyzer.async_load()

    status = json.loads(json.dumps(BASE_STATUS))
    registry = ir.async_get(hass)
    labels: list[str] = []
    seen_issues: set[str] = set()
    for frame in scenario["frames"]:
        status = _merge(status, frame.get("status") or {})
        coordinator.data = {"status": status}
        analyzer.analyze(status, now=float(frame["at"]))
        labels.extend(finding["label"] for finding in analyzer.findings)
        seen_issues.update(
            issue_id for (domain, issue_id) in registry.issues if domain == "advance_moonraker_control"
        )

    expected = scenario.get("expect") or {}
    for label in expected.get("findings") or []:
        assert any(label in finding_label for finding_label in labels), (
            f"{scenario['name']}: missing finding '{label}' in {labels}"
        )

    for key in expected.get("repairs") or []:
        assert f"replay_{scenario['name']}_{key}" in seen_issues, (
            f"{scenario['name']}: missing repairs issue '{key}'"
        )

    if "history_len" in expected:
        assert len(analyzer.print_history) == expected["history_len"]

    if "absent_findings" in expected:
        for label in expected["absent_findings"]:
            assert not any(label in finding_label for finding_label in labels), (
                f"{scenario['name']}: unexpected finding '{label}'"
            )

    if "mesh_status" in expected:
        assert analyzer.metrics.get("mesh_status") == expected["mesh_status"]

    await analyzer.async_shutdown()
