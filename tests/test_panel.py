"""Tests for the authenticated Moonraker control panel."""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import MoonrakerGcodeUploadView
from custom_components.moonraker.const import DOMAIN, METHODS

from .const import MOCK_CONFIG
from custom_components.moonraker.panel import (
    PANEL_GCODE_URL,
    _relative_gcode_path,
    PANEL_CLIENT_URL,
    PANEL_EMBED_URL,
    PANEL_FRONTEND_PATH,
    PANEL_I18N_URL,
    PANEL_MODULE_URL,
    MoonrakerPanelActionView,
    MoonrakerPanelClientView,
    MoonrakerPanelDataView,
    MoonrakerPanelEmbedView,
    MoonrakerPanelGcodeView,
    MoonrakerPanelI18nView,
    MoonrakerPanelModuleView,
    MoonrakerPanelParseView,
    MoonrakerPanelWorkerView,
    MoonrakerPanelThumbnailView,
    MoonrakerPanelView,
    MoonrakerUploadRedirectView,
    register_panel_views,
)


async def test_panel_redirects_to_authenticated_home_assistant_panel():
    """The legacy direct URL should redirect to the native frontend panel."""
    response = await MoonrakerPanelView().get(MagicMock())

    assert response.status == 302
    assert response.headers["Location"] == f"/{PANEL_FRONTEND_PATH}"


async def test_browser_ui_is_public_but_data_and_controls_require_auth():
    """Only static shell/assets and redirect routes are unauthenticated."""
    assert MoonrakerPanelView.requires_auth is False
    assert MoonrakerPanelEmbedView.requires_auth is False
    assert MoonrakerPanelModuleView.requires_auth is False
    assert MoonrakerPanelClientView.requires_auth is False
    assert MoonrakerPanelI18nView.requires_auth is False
    assert MoonrakerPanelParseView.requires_auth is False
    assert MoonrakerPanelWorkerView.requires_auth is False
    assert MoonrakerUploadRedirectView.requires_auth is False

    assert MoonrakerPanelDataView.requires_auth is True
    assert MoonrakerPanelGcodeView.requires_auth is True
    assert MoonrakerPanelThumbnailView.requires_auth is True
    assert MoonrakerPanelActionView.requires_auth is True
    assert MoonrakerGcodeUploadView.requires_auth is True


async def test_registers_custom_panel_with_ha_authenticated_connection():
    """Register a sidebar panel so its browser API calls use HA auth."""
    hass = MagicMock()
    hass.http.register_view = MagicMock()

    with patch(
        "homeassistant.components.panel_custom.async_register_panel",
        new_callable=AsyncMock,
    ) as register_panel:
        await register_panel_views(hass)

    registered_names = {
        call.args[0].name for call in hass.http.register_view.call_args_list
    }
    assert {
        "api:moonraker:panel",
        "api:moonraker:panel_embed",
        "api:moonraker:panel_module",
        "api:moonraker:panel_client",
        "api:moonraker:panel_i18n",
        "api:moonraker:toolpath_parse",
        "api:moonraker:toolpath_worker",
        "api:moonraker:gcode_upload_page",
        "api:moonraker:panel_data",
        "api:moonraker:panel_gcode",
        "api:moonraker:panel_thumbnail",
        "api:moonraker:panel_action",
    } <= registered_names
    register_panel.assert_awaited_once_with(
        hass,
        frontend_url_path=PANEL_FRONTEND_PATH,
        webcomponent_name="moonraker-control-panel",
        sidebar_title="Advance_Moonraker_Control",
        sidebar_icon="mdi:printer-3d",
        module_url=PANEL_MODULE_URL,
        embed_iframe=False,
        config={"frame_url": PANEL_EMBED_URL},
    )
    registered_urls = {
        view.url
        for call in hass.http.register_view.call_args_list
        if (view := call.args[0])
    }
    assert PANEL_CLIENT_URL in registered_urls
    assert PANEL_I18N_URL in registered_urls
    assert PANEL_GCODE_URL in registered_urls


async def test_panel_data_returns_all_discovered_cameras():
    """Expose every configured webcam so the camera page can build a grid."""
    coordinator = SimpleNamespace(
        config_entry=SimpleNamespace(
            entry_id="printer-id",
            data={"url": "printer.local", "port": 7125, "tls": False},
            options={},
        ),
        data={"status": {}, "file_list": {"files": []}},
        selected_file="",
        api_device_name="Test Printer",
        last_update_success=True,
        gcode_responses=[],
        query_obj={"objects": {}},
        polling_interval=timedelta(seconds=30),
        platforms=[],
        _printer_objects_list={"objects": []},
        async_get_webcams=AsyncMock(
            return_value={
                "webcams": [
                    {
                        "name": "Front",
                        "stream_url": "webcam/?action=stream",
                        "snapshot_url": "webcam/?action=snapshot",
                    },
                    {
                        "name": "Side",
                        "stream_url": "https://camera.local/side",
                        "snapshot_url": None,
                    },
                ]
            }
        ),
        async_get_system_info=AsyncMock(return_value={}),
        async_get_server_info=AsyncMock(
            return_value={
                "moonraker_version": "v0.9.3",
                "api_version": [1, 0, 0],
                "components": ["application", "authorization"],
                "failed_components": [],
            }
        ),
        analyzer=SimpleNamespace(
            as_dict=MagicMock(return_value={"metrics": {}, "findings": []})
        ),
    )
    view = MoonrakerPanelDataView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    view._coordinators = MagicMock(return_value={"printer-id": coordinator})

    response = await view.get(SimpleNamespace(query={"printer": "printer-id"}))

    assert response.status == 200
    payload = json.loads(response.text)
    webcams = payload["webcams"]
    assert payload["server_info"]["moonraker_version"] == "v0.9.3"
    assert [webcam["name"] for webcam in webcams] == ["Front", "Side"]
    assert webcams[0]["stream_url"] == "http://printer.local:7125/webcam/?action=stream"
    assert webcams[1]["stream_url"] == "https://camera.local/side"


@pytest.mark.parametrize("server_info_fails", [False, True])
async def test_panel_data_handles_unavailable_server_info(server_info_fails):
    """Keep system status usable when server.info is unavailable or malformed."""
    server_info_call = (
        AsyncMock(side_effect=UpdateFailed("server info unavailable"))
        if server_info_fails
        else AsyncMock(return_value=None)
    )
    coordinator = SimpleNamespace(
        config_entry=SimpleNamespace(
            entry_id="printer-id",
            data={"url": "printer.local", "port": 7125, "tls": False},
            options={},
        ),
        data={"status": {}, "file_list": []},
        selected_file=None,
        api_device_name="Test Printer",
        last_update_success=True,
        gcode_responses=[],
        query_obj={"objects": {}},
        polling_interval=timedelta(seconds=30),
        platforms=[],
        _printer_objects_list=None,
        async_get_webcams=AsyncMock(return_value={}),
        async_get_system_info=AsyncMock(return_value={}),
        async_get_server_info=server_info_call,
        analyzer=SimpleNamespace(
            as_dict=MagicMock(return_value={"metrics": {}, "findings": []})
        ),
    )
    view = MoonrakerPanelDataView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    view._coordinators = MagicMock(return_value={"printer-id": coordinator})

    response = await view.get(SimpleNamespace(query={"printer": "printer-id"}))

    assert json.loads(response.text)["server_info"] == {}


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("gcodes/part.gcode", "part.gcode"),
        ("/home/pi/printer_data/gcodes/sub/part.gcode", "sub/part.gcode"),
        ("sub\\part.gcode", "sub/part.gcode"),
        ("sub/gcodes/part.gcode", "sub/gcodes/part.gcode"),
        ("../printer.cfg", None),
        ("gcodes/../../printer.cfg", None),
        ("", None),
    ],
)
def test_relative_gcode_path(filename, expected):
    """Normalize gcode paths while rejecting traversal segments."""
    assert _relative_gcode_path(filename) == expected


async def test_gcode_proxy_rejects_non_active_file():
    """Only the active print file can be streamed for the 3D preview."""
    coordinator = SimpleNamespace(
        data={
            "status": {"print_stats": {"filename": "active.gcode"}},
            "file_list": {"files": [{"path": "active.gcode"}, {"path": "other.gcode"}]},
        }
    )
    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)

    response = await view.get(
        SimpleNamespace(query={"printer": "printer-id", "filename": "other.gcode"})
    )

    assert response.status == 404


async def test_gcode_proxy_streams_active_listed_file_with_moonraker_api_key():
    """The authenticated proxy streams the active file without exposing its key."""

    class MockContent:
        async def iter_chunked(self, _chunk_size):
            yield b"G1 X0 Y0 E0\n"
            yield b"G1 X10 Y10 E1\n"

    class MockUpstream:
        status = 200
        content_length = 26
        content = MockContent()

    class MockUpstreamContext:
        async def __aenter__(self):
            return MockUpstream()

        async def __aexit__(self, *_args):
            return False

    coordinator = SimpleNamespace(
        config_entry=SimpleNamespace(
            data={
                "url": "printer.local",
                "port": 7125,
                "tls": False,
                "api_key": "private-key",
            }
        ),
        data={
            "status": {"print_stats": {"filename": "parts/active.gcode"}},
            "file_list": {"files": [{"path": "parts/active.gcode"}]},
        },
    )
    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    session.get = MagicMock(return_value=MockUpstreamContext())
    stream_response = MagicMock()
    stream_response.prepare = AsyncMock()
    stream_response.write = AsyncMock()
    stream_response.write_eof = AsyncMock()
    request = SimpleNamespace(
        query={"printer": "printer-id", "filename": "gcodes/parts/active.gcode"}
    )

    with (
        patch(
            "custom_components.moonraker.panel.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.moonraker.panel.web.StreamResponse",
            return_value=stream_response,
        ) as stream_factory,
    ):
        response = await view.get(request)

    assert response is stream_response
    stream_factory.assert_called_once()
    assert session.get.call_args.args[0].endswith(
        "/server/files/gcodes/parts/active.gcode"
    )
    assert session.get.call_args.kwargs["headers"] == {"X-Api-Key": "private-key"}
    assert stream_response.write.await_count == 2
    stream_response.write_eof.assert_awaited_once()


def _panel_coordinator(hass, **overrides):
    """Build a SimpleNamespace coordinator double for panel view tests."""
    base = {
        "config_entry": SimpleNamespace(
            entry_id="printer-id",
            data={"url": "printer.local", "port": 7125, "tls": False},
            options={},
        ),
        "data": {"status": {}, "file_list": {"files": []}},
        "selected_file": None,
        "api_device_name": "Test Printer",
        "last_update_success": True,
        "gcode_responses": [],
        "query_obj": {"objects": {}},
        "polling_interval": timedelta(seconds=30),
        "platforms": [],
        "_printer_objects_list": {"objects": []},
        "async_get_webcams": AsyncMock(return_value={"webcams": []}),
        "async_get_system_info": AsyncMock(return_value={}),
        "async_get_server_info": AsyncMock(return_value={}),
        "async_get_config_settings": AsyncMock(return_value={}),
        "async_send_data": AsyncMock(),
        "async_refresh_files": AsyncMock(),
        "async_fetch_data": AsyncMock(return_value={}),
        "async_add_listener": MagicMock(return_value=lambda: None),
        "analyzer": SimpleNamespace(
            as_dict=MagicMock(return_value={"metrics": {}, "findings": []}),
            metrics={},
            findings=[],
            printcast=SimpleNamespace(forecast={}, mark_dried=lambda: True),
        ),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_resolve_coordinator_real_path(hass):
    """The real resolver returns coordinators from hass.data."""
    from custom_components.moonraker import MoonrakerDataUpdateCoordinator
    from custom_components.moonraker.panel import _resolve_coordinator

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="real")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="p"
    )
    hass.data.setdefault(DOMAIN, {})["real"] = coordinator
    hass.data[DOMAIN]["not-a-coordinator"] = object()

    assert _resolve_coordinator(hass, "real") is coordinator
    assert _resolve_coordinator(hass, None) is coordinator
    assert _resolve_coordinator(hass, "missing") is None

    hass.data[DOMAIN].clear()
    assert _resolve_coordinator(hass, None) is None


async def test_panel_view_base_resolve_uses_real_lookup(hass):
    """The view base helpers hit the module-level resolver."""
    from custom_components.moonraker import MoonrakerDataUpdateCoordinator

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="real")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="p"
    )
    hass.data.setdefault(DOMAIN, {})["real"] = coordinator

    view = MoonrakerPanelDataView(hass)
    assert view._resolve("real") is coordinator
    assert "real" in view._coordinators()

    response = await view.get(SimpleNamespace(query={"printer": "missing"}))
    assert response.status == 404


async def test_embed_and_asset_views_serve_files(hass):
    """Embed/module/client/upload views serve or redirect real assets."""
    embed = MoonrakerPanelEmbedView(hass)
    response = await embed.get(SimpleNamespace())
    assert response.status == 200
    assert "NEXUS" in response.text or "moonraker" in response.text.lower()

    module = MoonrakerPanelModuleView(hass)
    response = await module.get(SimpleNamespace())
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"

    client_view = MoonrakerPanelClientView(hass)
    response = await client_view.get(SimpleNamespace())
    assert response.status == 200

    i18n_view = MoonrakerPanelI18nView(hass)
    response = await i18n_view.get(SimpleNamespace())
    assert response.status == 200
    assert response.content_type == "application/javascript"
    assert "window.NEXUS_I18N" in response.text

    parse_view = MoonrakerPanelParseView(hass)
    response = await parse_view.get(SimpleNamespace())
    assert response.status == 200
    assert response.content_type == "application/javascript"
    assert "MoonrakerToolpathParse" in response.text

    worker_view = MoonrakerPanelWorkerView(hass)
    response = await worker_view.get(SimpleNamespace())
    assert response.status == 200
    assert response.content_type == "application/javascript"
    assert "toolpath_parse.js" in response.text

    redirect = await MoonrakerUploadRedirectView().get(SimpleNamespace())
    assert redirect.status == 302


async def test_panel_data_404_when_no_printer(hass):
    """panel_data rejects requests when nothing is configured."""
    view = MoonrakerPanelDataView(hass)
    response = await view.get(SimpleNamespace(query={}))
    assert response.status == 404


async def test_panel_payload_defensive_branches(hass):
    """Optional data sources degrade gracefully when absent or malformed."""
    from custom_components.moonraker import MoonrakerDataUpdateCoordinator
    from custom_components.moonraker.panel import _panel_payload

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="x")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="p"
    )
    coordinator.data = {
        "status": {"gcode_macro A": {}, "other": {}},
        "file_list": "not-a-dict",
    }

    async def _boom():
        raise RuntimeError("webcams down")

    async def _aux(method, params=None, quiet=False):
        if method == METHODS.MACHINE_DEVICE_POWER_DEVICES:
            return {"devices": [{"device": "led", "status": "on"}, "skip", {}]}
        return {}

    coordinator.async_fetch_data = AsyncMock(side_effect=_aux)
    coordinator.async_get_webcams = _boom
    coordinator.async_get_system_info = AsyncMock(
        return_value={"system_info": {"cpu_info": "nope"}}
    )
    coordinator.async_get_server_info = AsyncMock(return_value="not-a-dict")
    hass.data.setdefault(DOMAIN, {})["x"] = coordinator

    payload = await _panel_payload(hass, coordinator)

    assert payload["webcams"] == []
    assert payload["files"] == []
    assert payload["power_devices"] == [
        {"device": "led", "status": "on", "locked_while_printing": None}
    ]
    assert payload["server_info"] == {}
    assert payload["system_info"]["provider"] is None
    assert payload["macros"] == ["A"]

    # Non-dict webcam entries are skipped, and fetch failures degrade cleanly
    coordinator.async_get_webcams = AsyncMock(
        return_value={"webcams": ["not-a-dict", {"name": "cam"}]}
    )
    payload = await _panel_payload(hass, coordinator)
    assert [w["name"] for w in payload["webcams"]] == ["cam"]

    # system_info fetch failure and a non-dict payload both degrade
    coordinator.async_get_system_info = AsyncMock(
        side_effect=UpdateFailed("unavailable")
    )
    payload = await _panel_payload(hass, coordinator)
    assert payload["system_info"]["provider"] is None

    coordinator.async_get_system_info = AsyncMock(
        return_value={"system_info": "not-a-dict"}
    )
    payload = await _panel_payload(hass, coordinator)
    assert payload["system_info"]["provider"] is None

    hass.data[DOMAIN].pop("x")


async def test_gcode_proxy_rejects_unknown_and_unlisted(hass):
    """G-code proxy 404s for unknown printers and unlisted files."""
    view = MoonrakerPanelGcodeView(hass)
    response = await view.get(
        SimpleNamespace(query={"printer": "x", "filename": "a.gcode"})
    )
    assert response.status == 404

    coordinator = _panel_coordinator(
        hass,
        data={
            "status": {"print_stats": {"filename": "active.gcode"}},
            "file_list": {"files": []},
        },
    )
    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    response = await view.get(
        SimpleNamespace(query={"printer": "p", "filename": "active.gcode"})
    )
    assert response.status == 404


async def test_gcode_proxy_upstream_errors(hass):
    """Upstream non-200, oversize, and mid-stream failures map cleanly."""

    class _Ctx:
        def __init__(self, upstream):
            self._upstream = upstream

        async def __aenter__(self):
            return self._upstream

        async def __aexit__(self, *_):
            return False

    coordinator = _panel_coordinator(
        hass,
        data={
            "status": {"print_stats": {"filename": "active.gcode"}},
            "file_list": {"files": [{"path": "active.gcode"}]},
        },
    )
    request = SimpleNamespace(query={"printer": "p", "filename": "active.gcode"})

    # Upstream non-200 -> 404
    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    session.get = MagicMock(return_value=_Ctx(SimpleNamespace(status=503)))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(request)
    assert response.status == 404

    # Oversized Content-Length -> 413
    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    session.get = MagicMock(
        return_value=_Ctx(SimpleNamespace(status=200, content_length=10**9))
    )
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(request)
    assert response.status == 413

    # Stream exceeds cap mid-flight -> force_close, returns stream
    class _BigContent:
        async def iter_chunked(self, _n):
            yield b"x" * 10

    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    session.get = MagicMock(
        return_value=_Ctx(
            SimpleNamespace(status=200, content_length=None, content=_BigContent())
        )
    )
    stream_response = MagicMock()
    stream_response.prepare = AsyncMock()
    stream_response.write = AsyncMock()
    stream_response.write_eof = AsyncMock()
    with (
        patch(
            "custom_components.moonraker.panel.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.moonraker.panel.web.StreamResponse",
            return_value=stream_response,
        ),
        patch("custom_components.moonraker.panel._MAX_TOOLPATH_BYTES", 4),
    ):
        response = await view.get(request)
    assert response is stream_response
    stream_response.force_close.assert_called_once()

    # Connection error before streaming -> 502
    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("down"))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(request)
    assert response.status == 502

    # Connection error mid-stream -> force_close
    class _FailContent:
        async def iter_chunked(self, _n):
            yield b"ok"
            raise aiohttp.ClientError("reset")

    view = MoonrakerPanelGcodeView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    session.get = MagicMock(
        return_value=_Ctx(
            SimpleNamespace(status=200, content_length=None, content=_FailContent())
        )
    )
    stream_response = MagicMock()
    stream_response.prepare = AsyncMock()
    stream_response.write = AsyncMock()
    with (
        patch(
            "custom_components.moonraker.panel.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.moonraker.panel.web.StreamResponse",
            return_value=stream_response,
        ),
    ):
        response = await view.get(request)
    assert response is stream_response
    stream_response.force_close.assert_called_once()


def test_best_thumbnail_relative_path():
    """Thumbnail selection prefers the largest image and skips bad entries."""
    from custom_components.moonraker.panel import _best_thumbnail_relative_path

    assert _best_thumbnail_relative_path(None) is None
    assert _best_thumbnail_relative_path({"thumbnails": "nope"}) is None
    assert _best_thumbnail_relative_path({"thumbnails": []}) is None
    assert (
        _best_thumbnail_relative_path(
            {
                "thumbnails": [
                    "skip",
                    {"relative_path": ""},
                    {"relative_path": "small.png", "size": 10},
                    {"relative_path": "big.png", "size": 99},
                    {"relative_path": "odd.png", "size": "nan-ish"},
                ]
            }
        )
        == "big.png"
    )
    assert (
        _best_thumbnail_relative_path(
            {"thumbnails": [{"relative_path": "first.png", "size": "bad"}]}
        )
        == "first.png"
    )


async def test_file_meta_view(hass):
    """The file metadata endpoint whitelists fields and flags thumbnails."""
    from custom_components.moonraker.panel import MoonrakerPanelFileMetaView

    view = MoonrakerPanelFileMetaView(hass)
    response = await view.get(SimpleNamespace(query={}))
    assert response.status == 404

    coordinator = _panel_coordinator(hass)
    view = MoonrakerPanelFileMetaView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)

    response = await view.get(SimpleNamespace(query={}))
    assert response.status == 400

    response = await view.get(SimpleNamespace(query={"filename": "../x.gcode"}))
    assert response.status == 400

    coordinator.async_fetch_data = AsyncMock(side_effect=UpdateFailed("down"))
    response = await view.get(SimpleNamespace(query={"filename": "a.gcode"}))
    assert response.status == 502

    coordinator.async_fetch_data = AsyncMock(
        return_value={
            "estimated_time": 60,
            "secret_field": "hidden",
            "thumbnails": [{"relative_path": "t.png", "size": 1}],
        }
    )
    response = await view.get(SimpleNamespace(query={"filename": "a.gcode"}))
    payload = json.loads(response.text)
    assert payload["estimated_time"] == 60
    assert payload["has_thumbnail"] is True
    assert "secret_field" not in payload

    coordinator.async_fetch_data = AsyncMock(return_value="garbage")
    response = await view.get(SimpleNamespace(query={"filename": "a.gcode"}))
    assert json.loads(response.text)["has_thumbnail"] is False


async def test_thumbnail_view(hass):
    """The thumbnail proxy resolves, streams, and fails safely."""
    view = MoonrakerPanelThumbnailView(hass)
    response = await view.get(SimpleNamespace(query={}))
    assert response.status == 404

    coordinator = _panel_coordinator(hass)
    view = MoonrakerPanelThumbnailView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)

    # No thumbnail anywhere -> 404
    response = await view.get(SimpleNamespace(query={}))
    assert response.status == 404

    # Named file: metadata fetch fails -> 404
    coordinator.async_fetch_data = AsyncMock(side_effect=UpdateFailed("down"))
    response = await view.get(SimpleNamespace(query={"filename": "a.gcode"}))
    assert response.status == 404

    # Named file with a thumbnail -> proxied upstream
    coordinator.async_fetch_data = AsyncMock(
        return_value={
            "thumbnails": [
                {"relative_path": "small.png", "size": 1},
                {"relative_path": ".thumbs/big.png", "size": 100},
            ]
        }
    )

    class _Ctx:
        def __init__(self, upstream):
            self._upstream = upstream

        async def __aenter__(self):
            return self._upstream

        async def __aexit__(self, *_):
            return False

    session = MagicMock()
    upstream = SimpleNamespace(
        status=200, content_type="image/png", read=AsyncMock(return_value=b"png")
    )
    session.get = MagicMock(return_value=_Ctx(upstream))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(SimpleNamespace(query={"filename": "sub/a.gcode"}))
    assert response.status == 200
    assert response.content_type == "image/png"
    assert ".thumbs/big.png" in session.get.call_args.args[0]

    # Upstream non-200 -> 404
    session.get = MagicMock(return_value=_Ctx(SimpleNamespace(status=404)))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(SimpleNamespace(query={"filename": "sub/a.gcode"}))
    assert response.status == 404

    # Upstream error -> 502
    session.get = MagicMock(side_effect=aiohttp.ClientError("down"))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(SimpleNamespace(query={"filename": "sub/a.gcode"}))
    assert response.status == 502

    # Coordinator thumbnails_path fallback for the active job
    coordinator = _panel_coordinator(hass, data={"thumbnails_path": "dir/t.png"})
    view = MoonrakerPanelThumbnailView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)
    session = MagicMock()
    upstream = SimpleNamespace(
        status=200, content_type="image/png", read=AsyncMock(return_value=b"x")
    )
    session.get = MagicMock(return_value=_Ctx(upstream))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(SimpleNamespace(query={}))
    assert response.status == 200
    assert "dir/t.png" in session.get.call_args.args[0]


class _ActionRequest(dict):
    """Request double carrying hass_user for the admin gate."""

    def __init__(self, is_admin=True):
        super().__init__({"hass_user": SimpleNamespace(is_admin=is_admin)})
        self.json = AsyncMock()


async def _post_action(view, payload, is_admin=True):
    request = _ActionRequest(is_admin=is_admin)
    request.json = AsyncMock(return_value=payload)
    return await view.post(request)


def view_for(view, coordinator):
    """Point a view at a coordinator double."""
    view._resolve = MagicMock(return_value=coordinator)
    return view


async def test_action_view_request_handling(hass):
    """The action endpoint validates JSON, printers, and action failures."""
    view = MoonrakerPanelActionView(hass)

    request = _ActionRequest()
    request.json = AsyncMock(side_effect=ValueError("bad"))
    response = await view.post(request)
    assert response.status == 400

    response = await _post_action(view, {"action": "pause", "entry_id": "nope"})
    assert response.status == 404

    coordinator = _panel_coordinator(hass)
    view = MoonrakerPanelActionView(MagicMock())
    view._resolve = MagicMock(return_value=coordinator)

    coordinator.async_send_data = AsyncMock(side_effect=RuntimeError("blew up"))
    response = await _post_action(view, {"action": "pause", "entry_id": "p"})
    assert response.status == 502

    response = await _post_action(view, {"action": "bogus", "entry_id": "p"})
    assert response.status == 400

    coordinator.async_send_data = AsyncMock()
    response = await _post_action(view, {"action": "pause", "entry_id": "p"})
    assert response.status == 200
    coordinator.async_send_data.assert_awaited_once()


async def test_action_view_requires_admin(hass):
    """Non-admin users are denied unless the entry allows operators."""
    coordinator = _panel_coordinator(hass)
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(
        view, {"action": "pause", "entry_id": "p"}, is_admin=False
    )
    assert response.status == 403
    coordinator.async_send_data.assert_not_called()

    # missing user context is denied as well
    request = _ActionRequest(is_admin=True)
    request["hass_user"] = None
    request.json = AsyncMock(return_value={"action": "pause", "entry_id": "p"})
    response = await view.post(request)
    assert response.status == 403


async def test_action_view_operator_role(hass):
    """Operator role lets non-admins run the live-print allowlist only."""
    coordinator = _panel_coordinator(
        hass,
        config_entry=SimpleNamespace(
            entry_id="printer-id",
            data={},
            options={"panel_role": "operator"},
        ),
    )
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    for action in ("pause", "resume", "set_fan"):
        payload = {"action": action, "entry_id": "p"}
        if action == "set_fan":
            payload["value"] = 50
        response = await _post_action(view, payload, is_admin=False)
        assert response.status == 200

    for action in ("run_gcode", "cancel", "jog", "power", "delete_file"):
        response = await _post_action(
            view, {"action": action, "entry_id": "p"}, is_admin=False
        )
        assert response.status == 403


async def test_apply_queue_plan_action(hass):
    """Applying the analyzer's queue plan reposts jobs in plan order."""
    from custom_components.moonraker.const import METHODS

    coordinator = _panel_coordinator(hass)
    coordinator.analyzer = SimpleNamespace(
        metrics={
            "queue_plan": [
                {"job_id": "b", "filename": "quick.gcode", "ok": True},
                {"job_id": "a", "filename": "long.gcode", "ok": False},
            ]
        }
    )
    coordinator.data = {
        "queue": {
            "queued_jobs": [
                {"job_id": "a", "filename": "long.gcode"},
                {"job_id": "b", "filename": "quick.gcode"},
            ]
        }
    }
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(view, {"action": "apply_queue_plan", "entry_id": "p"})
    assert response.status == 200
    calls = coordinator.async_send_data.await_args_list
    assert calls[0].args[0] == METHODS.SERVER_JOB_QUEUE_DELETE_JOB
    assert calls[0].args[1] == {"job_ids": ["a", "b"]}
    assert calls[1].args[0] == METHODS.SERVER_JOB_QUEUE_POST_JOB
    assert calls[1].args[1] == {"filenames": ["quick.gcode", "long.gcode"]}

    # no plan → 400 without touching the queue
    coordinator.analyzer.metrics["queue_plan"] = []
    coordinator.async_send_data.reset_mock()
    response = await _post_action(view, {"action": "apply_queue_plan", "entry_id": "p"})
    assert response.status == 400
    coordinator.async_send_data.assert_not_called()


@pytest.mark.parametrize(
    "action",
    [
        "pause",
        "resume",
        "cancel",
        "emergency_stop",
        "firmware_restart",
        "server_restart",
        "host_restart",
        "host_shutdown",
        "machine_update_refresh",
        "start_queue",
    ],
)
async def test_direct_actions_send_mapped_method(action):
    """Every direct panel action forwards its Moonraker method."""
    from custom_components.moonraker.panel import _DIRECT_ACTIONS

    coordinator = _panel_coordinator(MagicMock())
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)
    response = await _post_action(view, {"action": action, "entry_id": "p"})
    assert response.status == 200
    coordinator.async_send_data.assert_awaited_once_with(_DIRECT_ACTIONS[action])


async def test_jog_action_validation_and_scripts():
    """Jog validates axis/distance and emits relative moves."""
    coordinator = _panel_coordinator(MagicMock())
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(view, {"action": "jog", "axis": "X", "dist": "abc"})
    assert response.status == 400

    response = await _post_action(view, {"action": "jog", "axis": "Q", "dist": 1})
    assert response.status == 400

    response = await _post_action(view, {"action": "jog", "axis": "z", "dist": 0.1})
    assert response.status == 200
    script = coordinator.async_send_data.await_args.args[1]["script"]
    assert "G1 Z0.1 F600" in script and "G91" in script

    await _post_action(view, {"action": "jog", "axis": "X", "dist": 10})
    assert "F6000" in coordinator.async_send_data.await_args.args[1]["script"]


async def test_preheat_and_script_actions():
    """Preheat presets and raw scripts send the right g-code."""
    coordinator = _panel_coordinator(MagicMock())
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(view, {"action": "preheat", "preset": "nope"})
    assert response.status == 400

    await _post_action(view, {"action": "preheat", "preset": "PLA"})
    assert (
        coordinator.async_send_data.await_args.args[1]["script"]
        == "M104 S200\nM140 S60"
    )

    response = await _post_action(view, {"action": "run_gcode", "script": "  "})
    assert response.status == 400

    await _post_action(view, {"action": "run_macro", "script": "M600"})
    assert coordinator.async_send_data.await_args.args[1]["script"] == "M600"


async def test_file_actions():
    """Select, print, enqueue, and delete file actions route correctly."""
    from custom_components.moonraker.const import METHODS

    coordinator = _panel_coordinator(MagicMock())
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(view, {"action": "print_file"})
    assert response.status == 400

    await _post_action(view, {"action": "select_file", "filename": "a.gcode"})
    assert coordinator.selected_file == "a.gcode"

    await _post_action(view, {"action": "print_file", "filename": "b.gcode"})
    assert coordinator.selected_file == "b.gcode"
    coordinator.async_send_data.assert_awaited_with(
        METHODS.PRINTER_PRINT_START, {"filename": "b.gcode"}
    )

    await _post_action(view, {"action": "enqueue_file", "filename": "c.gcode"})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.SERVER_JOB_QUEUE_POST_JOB, {"filenames": ["c.gcode"]}
    )

    response = await _post_action(view, {"action": "delete_file"})
    assert response.status == 400

    await _post_action(view, {"action": "delete_file", "filename": "c.gcode"})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.SERVER_FILES_DELETE_FILE, {"path": "c.gcode"}
    )
    coordinator.async_refresh_files.assert_awaited()


async def test_power_and_queue_actions():
    """Power device toggles and queue management actions route correctly."""
    from custom_components.moonraker.const import METHODS

    coordinator = _panel_coordinator(MagicMock())
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(view, {"action": "power", "device": "led"})
    assert response.status == 400

    await _post_action(
        view, {"action": "power", "device": "led", "power_action": "OFF"}
    )
    coordinator.async_send_data.assert_awaited_with(
        METHODS.MACHINE_DEVICE_POWER_POST_DEVICE,
        {"device": "led", "action": "off"},
    )

    await _post_action(view, {"action": "pause_queue"})
    coordinator.async_send_data.assert_awaited_with(METHODS.SERVER_JOB_QUEUE_PAUSE)

    response = await _post_action(view, {"action": "delete_queue_job"})
    assert response.status == 400

    await _post_action(view, {"action": "delete_queue_job", "job_id": "j1"})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.SERVER_JOB_QUEUE_DELETE_JOB, {"job_ids": ["j1"]}
    )

    await _post_action(view, {"action": "jump_queue_job", "job_id": "j2"})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.SERVER_JOB_QUEUE_JUMP, {"job_id": "j2"}
    )

    await _post_action(view, {"action": "refresh_files"})
    coordinator.async_refresh_files.assert_awaited()


async def test_gcode_actions():
    """Parameterized and fixed g-code actions validate and format values."""
    from custom_components.moonraker.const import METHODS

    coordinator = _panel_coordinator(MagicMock())
    view = view_for(MoonrakerPanelActionView(MagicMock()), coordinator)

    response = await _post_action(view, {"action": "set_speed", "value": "abc"})
    assert response.status == 400

    await _post_action(view, {"action": "set_speed", "value": 150})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.PRINTER_GCODE_SCRIPT, {"script": "M220 S150.0"}
    )

    await _post_action(view, {"action": "motors_off"})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.PRINTER_GCODE_SCRIPT, {"script": "M84"}
    )

    await _post_action(view, {"action": "probe_mesh"})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.PRINTER_GCODE_SCRIPT, {"script": "BED_MESH_CALIBRATE"}
    )

    await _post_action(view, {"action": "z_adjust", "value": -0.05})
    coordinator.async_send_data.assert_awaited_with(
        METHODS.PRINTER_GCODE_SCRIPT, {"script": "SET_GCODE_OFFSET Z_ADJUST=-0.05"}
    )


async def test_panel_subscribe_websocket(hass):
    """The websocket subscription pushes snapshots on coordinator updates."""
    from custom_components.moonraker import MoonrakerDataUpdateCoordinator
    from custom_components.moonraker.panel import _ws_panel_subscribe

    connection = SimpleNamespace(
        subscriptions={},
        send_error=MagicMock(),
        send_result=MagicMock(),
        send_message=MagicMock(),
    )
    msg = {"id": 7, "type": "moonraker/panel_subscribe", "entry_id": "missing"}
    hass.data[DOMAIN] = {}
    _ws_panel_subscribe(hass, connection, msg)
    await hass.async_block_till_done(wait_background_tasks=True)
    connection.send_error.assert_called_once_with(
        7, "not_found", "No printer configured"
    )

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="p")
    coordinator = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="p"
    )
    coordinator.data = {"status": {}}
    coordinator.async_get_webcams = AsyncMock(return_value={})
    coordinator.async_get_system_info = AsyncMock(return_value={})
    coordinator.async_get_server_info = AsyncMock(return_value={})
    hass.data[DOMAIN] = {"p": coordinator}
    msg = {"id": 7, "type": "moonraker/panel_subscribe", "entry_id": "p"}

    _ws_panel_subscribe(hass, connection, msg)
    await hass.async_block_till_done(wait_background_tasks=True)
    connection.send_result.assert_called_once_with(7)
    assert connection.send_message.called
    assert 7 in connection.subscriptions

    # A coordinator update fires the push task
    connection.send_message.reset_mock()
    coordinator.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert connection.send_message.called

    # A broken payload builder logs but never kills the subscription
    connection.send_message.reset_mock()
    with patch(
        "custom_components.moonraker.panel._panel_payload",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        coordinator.async_update_listeners()
        await hass.async_block_till_done(wait_background_tasks=True)
    assert not connection.send_message.called


async def test_panel_payload_includes_aux_data_and_console(hass):
    """Power, queue, history, and gcode store feed the panel payload."""
    from custom_components.moonraker.panel import _panel_payload

    async def _fetch(method, params=None, quiet=False):
        return {
            "machine.device_power.devices": {
                "devices": [{"device": "printer", "status": "on"}]
            },
            "server.job_queue.status": {
                "queue_state": "ready",
                "queued_jobs": [{"job_id": "1", "filename": "a.gcode"}],
            },
            "server.history.totals": {"job_totals": {"total_jobs": 4}},
            "machine.update.status": {"version_info": {"klipper": {"version": "v1"}}},
            "server.spoolman.status": {"spool_id": 12},
            "server.gcode_store": {
                "gcode_store": [
                    {"message": "old line"},
                    {"message": "dup"},
                    "skip",
                ]
            },
        }[method.value]

    coordinator = _panel_coordinator(
        hass,
        async_fetch_data=AsyncMock(side_effect=_fetch),
        gcode_responses=["dup", "new line"],
    )

    payload = await _panel_payload(hass, coordinator)

    assert payload["power_devices"][0]["device"] == "printer"
    assert payload["queue"]["queued_jobs"][0]["filename"] == "a.gcode"
    assert payload["history"]["job_totals"]["total_jobs"] == 4
    assert payload["machine_update"]["version_info"]["klipper"]["version"] == "v1"
    assert payload["spoolman"]["spool_id"] == 12
    assert payload["gcode_responses"] == ["old line", "dup", "new line"]

    # Second call hits the aux cache rather than Moonraker again.
    coordinator.async_fetch_data.reset_mock()
    payload2 = await _panel_payload(hass, coordinator)
    assert payload2["queue"]["queue_state"] == "ready"
    coordinator.async_fetch_data.assert_not_awaited()


async def test_panel_aux_data_failure_paths(hass):
    """Aux fetch failures degrade to empty structures and cache."""
    from custom_components.moonraker.panel import _panel_aux_data

    calls = {"n": 0}

    async def _flaky(method, params=None, quiet=False):
        calls["n"] += 1
        if method.value == "machine.device_power.devices":
            raise UpdateFailed("down")
        if method.value == "server.gcode_store":
            raise RuntimeError("unexpected")
        return "not-a-dict"

    coordinator = _panel_coordinator(
        hass, async_fetch_data=AsyncMock(side_effect=_flaky)
    )
    aux = await _panel_aux_data(coordinator)
    assert aux == {}
    assert calls["n"] == 6

    # TTL cache serves a repeat call without touching Moonraker.
    assert await _panel_aux_data(coordinator) == aux
    assert calls["n"] == 6


async def test_panel_aux_data_coalesces_concurrent_fetches(hass):
    """Concurrent panel connections share one batch of auxiliary requests."""
    from custom_components.moonraker.panel import _panel_aux_data

    calls = 0

    async def _fetch(method, params=None, quiet=False):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"method": method.value}

    coordinator = _panel_coordinator(
        hass, async_fetch_data=AsyncMock(side_effect=_fetch)
    )
    first, second = await asyncio.gather(
        _panel_aux_data(coordinator), _panel_aux_data(coordinator)
    )
    assert first == second
    assert calls == 6


async def test_console_lines_merges_store_and_live(hass):
    """Console output combines stored gcode lines with live pushes."""
    from custom_components.moonraker.panel import _console_lines

    coordinator = _panel_coordinator(hass, gcode_responses=["b", "c"])
    assert _console_lines(
        coordinator, {"gcode_store": [{"message": "a"}, {"message": "b"}]}
    ) == ["a", "b", "c"]
    assert _console_lines(coordinator, None) == ["b", "c"]
    assert _console_lines(coordinator, {"gcode_store": "bad"}) == ["b", "c"]


def test_parse_screws_tilt_klipper_output():
    """SCREWS_TILT_CALCULATE output yields per-screw turns and direction."""
    from custom_components.moonraker.panel import _parse_screws_tilt

    lines = [
        "Send: SCREWS_TILT_CALCULATE",
        "// front left screw (base) : x=30.0, y=30.0, z=0.02250",
        "// front right screw : x=230.0, y=30.0, z=0.15250 : adjust CW 00:10",
        "// rear right screw : x=230.0, y=230.0, z=-0.10000 : adjust CCW 01:35",
        "// rear left screw : x=30.0, y=230.0, z=0.30000 : adjust CW 2:96",
        "ok",
    ]
    result = _parse_screws_tilt(lines)
    assert result["calibrated"] is True
    assert result["base"] == "front left screw"
    screws = result["screws"]
    assert len(screws) == 4
    assert screws[0]["base"] is True
    assert screws[0]["turns"] is None
    assert screws[1]["direction"] == "CW"
    assert screws[1]["turns"] == pytest.approx(10 / 60)
    assert screws[2]["direction"] == "CCW"
    assert screws[2]["turns"] == pytest.approx((60 + 35) / 60)
    # Nonstandard clock values still normalize to fractional turns.
    assert screws[3]["turns"] == pytest.approx((120 + 96) / 60)


def test_parse_screws_tilt_uses_newest_block_and_ignores_noise():
    """Only the last SCREWS_TILT_CALCULATE run is reported."""
    from custom_components.moonraker.panel import _parse_screws_tilt

    lines = [
        "Send: SCREWS_TILT_CALCULATE",
        "screw1 (base) : x=1.0, y=1.0, z=0.1 : adjust CW 00:05",
        "unrelated junk",
        "Send: SCREWS_TILT_CALCULATE",
        "screwA (base) : x=2.0, y=2.0, z=0.2",
        "screwB : x=3.0, y=3.0, z=0.3 : adjust CCW 00:15",
    ]
    result = _parse_screws_tilt(lines)
    assert [s["name"] for s in result["screws"]] == ["screwa", "screwb"]
    assert _parse_screws_tilt([]) == {}
    assert _parse_screws_tilt(["no calibration here"]) == {}


def test_parse_probe_calibrate_and_seen_commands():
    """PROBE_CALIBRATE z_offset and command presence are detected."""
    from custom_components.moonraker.panel import (
        _calibration_seen,
        _parse_probe_calibrate,
    )

    lines = [
        "Send: PROBE_CALIBRATE",
        "// probe: z_offset: 2.345",
        "Send: BED_MESH_CALIBRATE",
        "// probe: z_offset: 2.500",
    ]
    assert _parse_probe_calibrate(lines) == pytest.approx(2.5)
    assert _parse_probe_calibrate(["z_offset = not-a-number"]) is None
    assert _parse_probe_calibrate([]) is None
    seen = _calibration_seen(lines)
    assert seen == {
        "bed_mesh": True,
        "screws_tilt": False,
        "probe_calibrate": True,
    }
    assert _calibration_seen([]) == {
        "bed_mesh": False,
        "screws_tilt": False,
        "probe_calibrate": False,
    }


async def test_panel_payload_includes_calibration(hass):
    """Console history feeds the calibration block in the panel payload."""
    from custom_components.moonraker.panel import _panel_payload

    coordinator = _panel_coordinator(
        hass,
        gcode_responses=[
            "Send: SCREWS_TILT_CALCULATE",
            "screw1 (base) : x=30.0, y=30.0, z=0.02",
            "screw2 : x=230.0, y=30.0, z=0.15 : adjust CW 00:10",
        ],
    )
    payload = await _panel_payload(hass, coordinator)
    calibration = payload["calibration"]
    assert calibration["calibrated"] is True
    assert calibration["screws"][1]["direction"] == "CW"
    assert calibration["screws"][1]["turns"] == pytest.approx(10 / 60)
    assert calibration["seen"]["screws_tilt"] is True
    assert calibration["probe_z_offset"] is None


async def test_panel_payload_layers_and_klippy(hass):
    """The payload exposes computed layer counters and printer state."""
    from custom_components.moonraker.panel import _panel_payload

    coordinator = _panel_coordinator(
        hass,
        data={
            "status": {
                "print_stats": {
                    "state": "printing",
                    "print_duration": 120,
                    "filename": "job.gcode",
                    "info": {},
                },
                "virtual_sdcard": {},
                "toolhead": {"position": [1, 2, 4.2, 5]},
            },
            "file_list": {"files": []},
            "printer.info": {"state": "ready"},
            "layer_height": 0.2,
            "first_layer_height": 0.2,
            "object_height": 10,
            "layer_count": 50,
        },
    )
    payload = await _panel_payload(hass, coordinator)
    assert payload["layers"]["current"] == 21
    assert payload["layers"]["total"] == 50
    assert payload["printer_info"]["state"] == "ready"


async def test_webcam_snapshot_view(hass):
    """The snapshot proxy serves the named webcam's latest frame."""
    from custom_components.moonraker.panel import MoonrakerPanelSnapshotView

    view = MoonrakerPanelSnapshotView(hass)
    response = await view.get(SimpleNamespace(query={"printer": "x"}))
    assert response.status == 404

    session = MagicMock()
    upstream = MagicMock()
    upstream.status = 200
    upstream.content_type = "image/jpeg"
    upstream.read = AsyncMock(return_value=b"JPEG")
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=upstream)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    coordinator = _panel_coordinator(
        hass,
        async_get_webcams=AsyncMock(
            return_value={
                "webcams": [{"name": "Front", "snapshot_url": "webcam?action=snapshot"}]
            }
        ),
    )
    view._resolve = MagicMock(return_value=coordinator)

    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        missing = await view.get(SimpleNamespace(query={}))
        assert missing.status == 400
        response = await view.get(SimpleNamespace(query={"camera": "Front"}))
    assert response.status == 200
    assert response.body == b"JPEG"
    session.get.assert_called_once()

    response = await view.get(SimpleNamespace(query={"camera": "Nope"}))
    assert response.status == 404

    coordinator.async_get_webcams = AsyncMock(side_effect=RuntimeError("boom"))
    response = await view.get(SimpleNamespace(query={"camera": "Front"}))
    assert response.status == 502

    coordinator.async_get_webcams = AsyncMock(
        return_value={"webcams": [{"name": "Front", "snapshot_url": "x"}]}
    )
    session.get = MagicMock(side_effect=aiohttp.ClientError("down"))
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(SimpleNamespace(query={"camera": "Front"}))
    assert response.status == 502

    upstream.status = 500
    session.get = MagicMock(return_value=ctx)
    with patch(
        "custom_components.moonraker.panel.async_get_clientsession",
        return_value=session,
    ):
        response = await view.get(SimpleNamespace(query={"camera": "Front"}))
    assert response.status == 404


def test_spool_details_whitelist():
    """Spool records are trimmed to display-safe fields."""
    from custom_components.moonraker.panel import _spool_details

    assert _spool_details("not-a-dict") == {}
    assert _spool_details({}) == {"filament": {}}
    spool = {
        "id": 7,
        "remaining_weight": 420.5,
        "used_weight": 79.5,
        "remaining_length": 140000.0,
        "used_length": 26000.0,
        "comment": "private note",
        "filament": {
            "name": "PLA Pro",
            "material": "PLA",
            "vendor": "VendorCo",
            "diameter": 1.75,
            "density": 1.24,
            "color_hex": "00ff00",
            "comment": "internal",
        },
    }
    details = _spool_details(spool)
    assert details["id"] == 7
    assert details["remaining_weight"] == 420.5
    assert details["filament"] == {
        "name": "PLA Pro",
        "material": "PLA",
        "vendor": "VendorCo",
        "diameter": 1.75,
        "density": 1.24,
        "color_hex": "00ff00",
    }
    assert "comment" not in details
    assert "comment" not in details["filament"]


def test_bed_bounds_extraction():
    """Bed bounds pull numeric axis limits out of configfile settings."""
    from custom_components.moonraker.panel import _bed_bounds

    settings = {
        "status": {
            "configfile": {
                "settings": {
                    "stepper_x": {"position_min": 0.0, "position_max": 235.0},
                    "stepper_y": {"position_min": 0.0, "position_max": 235.0},
                    "stepper_z": {"position_max": "not-a-number"},
                    "stepper_x2": "not-a-dict",
                    "fan": {"pin": "PA0"},
                }
            }
        }
    }
    assert _bed_bounds(settings) == {
        "x": {"min": 0.0, "max": 235.0},
        "y": {"min": 0.0, "max": 235.0},
    }
    assert _bed_bounds({}) == {}
    assert _bed_bounds(None) == {}
    assert _bed_bounds({"status": "bad"}) == {}


def test_fleet_summary_variants(hass):
    """Fleet tiles summarize each coordinator's cached status."""
    from custom_components.moonraker.panel import _fleet_summary

    coordinator = _panel_coordinator(
        hass,
        data={
            "status": {
                "print_stats": {"state": "printing", "filename": "job.gcode"},
                "display_status": {"progress": 0.42},
                "extruder": {"temperature": 210.0},
                "heater_bed": {"temperature": 60.0},
            }
        },
    )
    summary = _fleet_summary(coordinator)
    assert summary == {
        "id": "printer-id",
        "name": "Test Printer",
        "available": True,
        "state": "printing",
        "progress": 0.42,
        "hotend": 210.0,
        "bed": 60.0,
        "filename": "job.gcode",
        "material": None,
        "ambient_c": None,
        "oee": {
            "utilization_pct": None,
            "success_rate_pct": None,
            "throughput_gh": None,
        },
    }

    coordinator.data = {"status": {"virtual_sdcard": {"progress": 0.5}}}
    assert _fleet_summary(coordinator)["progress"] == 0.5
    coordinator.data = {"status": {"display_status": {"progress": "bad"}}}
    assert _fleet_summary(coordinator)["progress"] is None
    coordinator.data = None
    summary = _fleet_summary(coordinator)
    assert summary["state"] is None
    assert summary["progress"] is None


async def test_panel_aux_fetches_spool_details(hass):
    """An active Spoolman spool triggers a proxied detail lookup."""
    from custom_components.moonraker.panel import _panel_aux_data

    async def _fetch(method, params=None, quiet=False):
        if method.value == "server.spoolman.status":
            return {"spool_id": 12}
        if method.value == "server.spoolman.proxy":
            return {
                "id": 12,
                "remaining_weight": 100.0,
                "filament": {"name": "PLA"},
            }
        return {}

    coordinator = _panel_coordinator(
        hass, async_fetch_data=AsyncMock(side_effect=_fetch)
    )
    aux = await _panel_aux_data(coordinator)
    assert aux["spool_details"]["remaining_weight"] == 100.0
    proxy_call = coordinator.async_fetch_data.await_args_list[-1]
    assert proxy_call.args[0].value == "server.spoolman.proxy"
    assert proxy_call.args[1] == {
        "request_method": "GET",
        "path": "/api/v1/spool/12",
    }

    # A non-dict proxy reply is discarded.
    async def _bad_proxy(method, params=None, quiet=False):
        if method.value == "server.spoolman.status":
            return {"spool_id": 9}
        if method.value == "server.spoolman.proxy":
            return "broken"
        return {}

    coordinator = _panel_coordinator(
        hass, async_fetch_data=AsyncMock(side_effect=_bad_proxy)
    )
    assert "spool_details" not in await _panel_aux_data(coordinator)


async def test_panel_payload_fleet_bed_bounds_and_spool(hass):
    """The payload exposes fleet summaries, bed bounds, and spool details."""
    from custom_components.moonraker import MoonrakerDataUpdateCoordinator
    from custom_components.moonraker.panel import _panel_payload

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="real")
    real = MoonrakerDataUpdateCoordinator(
        hass, client=MagicMock(), config_entry=config_entry, api_device_name="p"
    )
    real.data = {
        "status": {
            "print_stats": {"state": "printing", "filename": "job.gcode"},
            "display_status": {"progress": 0.5},
            "extruder": {"temperature": 200.0},
            "heater_bed": {"temperature": 60.0},
        }
    }
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = real

    async def _fetch(method, params=None, quiet=False):
        if method.value == "server.spoolman.status":
            return {"spool_id": 3}
        if method.value == "server.spoolman.proxy":
            return {
                "id": 3,
                "remaining_weight": 50.0,
                "filament": {"material": "PETG", "secret": "x"},
            }
        return {}

    coordinator = _panel_coordinator(
        hass,
        async_fetch_data=AsyncMock(side_effect=_fetch),
        async_get_config_settings=AsyncMock(
            return_value={
                "status": {
                    "configfile": {"settings": {"stepper_x": {"position_max": 235.0}}}
                }
            }
        ),
    )

    payload = await _panel_payload(hass, coordinator)
    assert payload["bed_bounds"] == {"x": {"max": 235.0}}
    assert payload["spool_details"]["filament"] == {"material": "PETG"}
    assert payload["fleet"] == [
        {
            "id": "real",
            "name": "p",
            "available": real.last_update_success,
            "state": "printing",
            "progress": 0.5,
            "hotend": 200.0,
            "bed": 60.0,
            "filename": "job.gcode",
            "material": None,
            "ambient_c": None,
            "oee": {
                "utilization_pct": None,
                "success_rate_pct": None,
                "throughput_gh": None,
            },
        }
    ]

    # A config-settings failure degrades to empty bounds.
    coordinator.async_get_config_settings = AsyncMock(side_effect=UpdateFailed("down"))
    payload2 = await _panel_payload(hass, coordinator)
    assert payload2["bed_bounds"] == {}

    hass.data[DOMAIN].pop("real")


def test_route_needs_picks_first_real_job(hass):
    """Route needs summarize the first queued job with metadata."""
    from custom_components.moonraker.panel import _route_needs

    coordinator = _panel_coordinator(hass, data={"queue": {"queued_jobs": "bad"}})
    assert _route_needs(coordinator) == {}

    coordinator = _panel_coordinator(
        hass,
        data={
            "queue": {"queued_jobs": [{"job_id": "1"}, {"filename": "a.gcode"}]},
            "queue_meta": {
                "a.gcode": {"filament_total": 5000.0, "filament_type": "ABS"}
            },
        },
    )
    assert _route_needs(coordinator) == {
        "filename": "a.gcode",
        "filament_mm": 5000.0,
        "material": "ABS",
    }

    coordinator = _panel_coordinator(
        hass, data={"queue": {"queued_jobs": [{"filename": "b.gcode"}]}}
    )
    assert _route_needs(coordinator)["filament_mm"] is None

    coordinator = _panel_coordinator(
        hass, data={"queue": {"queued_jobs": [{"job_id": "1"}, "junk"]}}
    )
    assert _route_needs(coordinator) == {}


def test_route_score_weights_fitness(hass):
    """The router scores idle, compatible printers highest."""
    from custom_components.moonraker.panel import _route_score

    offline = _panel_coordinator(hass)
    offline.last_update_success = False
    assert _route_score(offline, {}) == {"score": 0, "reasons": ["offline"]}

    busy = _panel_coordinator(
        hass,
        data={"status": {"print_stats": {"state": "printing"}}},
    )
    busy.analyzer.metrics = {
        "spool_material": "PLA",
        "spool_remaining_mm": 100.0,
        "preflight": {"mesh_fresh": False},
        "ambient_c": 10.0,
    }
    result = _route_score(busy, {"filament_mm": 5000.0, "material": "ABS"})
    assert result["score"] == 10
    assert "busy (printing)" in result["reasons"]
    assert "loaded PLA" in result["reasons"]
    assert "insufficient filament" in result["reasons"]
    assert "stale mesh" in result["reasons"]
    assert "cold chamber" not in result["reasons"]  # PLA is not high-shrink

    cold = _panel_coordinator(
        hass,
        data={"status": {"print_stats": {"state": "standby"}}},
    )
    cold.analyzer.metrics = {
        "spool_material": "ABS",
        "ambient_c": 10.0,
    }
    result = _route_score(cold, {})
    assert result["score"] == 90
    assert "cold chamber" in result["reasons"]

    ideal = _panel_coordinator(
        hass,
        data={"status": {"print_stats": {"state": "standby"}}},
    )
    ideal.analyzer.metrics = {
        "spool_material": "ABS+",
        "spool_remaining_mm": 9000.0,
        "preflight": {"mesh_fresh": True},
        "ambient_c": 35.0,
    }
    result = _route_score(ideal, {"filament_mm": 5000.0, "material": "ABS"})
    assert result == {"score": 100, "reasons": []}


async def test_panel_pwa_manifest_and_service_worker(hass):
    """The PWA manifest and service worker routes serve install metadata."""
    from custom_components.moonraker.panel import (
        MoonrakerPanelManifestView,
        MoonrakerPanelServiceWorkerView,
    )

    manifest = await MoonrakerPanelManifestView().get(MagicMock())
    import json

    body = json.loads(manifest.body.decode())
    assert body["name"] == "Advance_Moonraker_Control"
    assert body["display"] == "standalone"
    assert body["scope"] == "/api/moonraker/"

    worker = await MoonrakerPanelServiceWorkerView().get(MagicMock())
    assert worker.content_type == "application/javascript"
    assert b"service worker" in worker.body


async def test_panel_printcast_endpoint(hass):
    """The printcast endpoint scores arbitrary files against live state."""
    import json

    from custom_components.moonraker.panel import MoonrakerPanelPrintcastView

    view = MoonrakerPanelPrintcastView(hass)
    coordinator = _panel_coordinator(hass)
    coordinator.analyzer.printcast = SimpleNamespace(
        forecast={},
        build_forecast=MagicMock(
            return_value={
                "filename": "part.gcode",
                "score": 92,
                "verdict": "CLEAR",
                "factors": [],
            }
        ),
    )
    view._resolve = MagicMock(return_value=coordinator)

    response = await view.get(
        SimpleNamespace(query={"printer": "printer-id", "filename": "part.gcode"})
    )
    assert response.status == 200
    body = json.loads(response.body.decode())
    assert body["score"] == 92
    coordinator.analyzer.printcast.build_forecast.assert_called_once()

    # Metadata fetch failure still yields a forecast.
    coordinator.async_fetch_data.side_effect = UpdateFailed("down")
    response = await view.get(
        SimpleNamespace(query={"printer": "printer-id", "filename": "part.gcode"})
    )
    assert response.status == 200

    # Non-dict metadata is tolerated.
    coordinator.async_fetch_data.side_effect = None
    coordinator.async_fetch_data.return_value = ["unexpected"]
    response = await view.get(
        SimpleNamespace(query={"printer": "printer-id", "filename": "part.gcode"})
    )
    assert response.status == 200

    # Path traversal is rejected before any metadata call.
    response = await view.get(
        SimpleNamespace(query={"printer": "printer-id", "filename": "../secret.txt"})
    )
    assert response.status == 400

    # Error paths.
    response = await view.get(SimpleNamespace(query={"printer": "printer-id"}))
    assert response.status == 400
    view._resolve = MagicMock(return_value=None)
    response = await view.get(
        SimpleNamespace(query={"printer": "ghost", "filename": "x"})
    )
    assert response.status == 404


async def test_panel_action_mark_spool_dried(hass):
    """The mark_spool_dried action resets dose without printer calls."""
    from custom_components.moonraker.panel import MoonrakerPanelActionView

    view = MoonrakerPanelActionView(hass)
    coordinator = _panel_coordinator(hass)
    view._resolve = MagicMock(return_value=coordinator)
    request = SimpleNamespace(
        json=AsyncMock(
            return_value={
                "entry_id": "printer-id",
                "action": "mark_spool_dried",
            }
        ),
        get=MagicMock(return_value=SimpleNamespace(is_admin=True, name="boss")),
    )
    response = await view.post(request)
    assert response.status == 200
    coordinator.async_send_data.assert_not_called()

    coordinator.analyzer.printcast.mark_dried = lambda: False
    response = await view.post(request)
    assert response.status == 400


def test_route_score_penalizes_low_printcast(hass):
    """A printer forecasting poorly loses router points."""
    from custom_components.moonraker.panel import _route_score

    candidate = _panel_coordinator(
        hass, data={"status": {"print_stats": {"state": "standby"}}}
    )
    candidate.analyzer.metrics = {
        "spool_material": "PLA",
        "spool_remaining_mm": 9000.0,
        "preflight": {"mesh_fresh": True},
        "ambient_c": 22.0,
        "printability_score": 35.0,
    }
    result = _route_score(candidate, {})
    assert result["score"] == 90
    assert "low printcast (35)" in result["reasons"]


async def test_payload_includes_printcast(hass):
    """The panel payload ships the live forecast dict."""
    coordinator = _panel_coordinator(hass)
    coordinator.analyzer.printcast.forecast = {
        "score": 88,
        "verdict": "CLEAR",
    }
    from custom_components.moonraker.panel import _panel_payload

    payload = await _panel_payload(hass, coordinator)
    assert payload["printcast"]["score"] == 88
