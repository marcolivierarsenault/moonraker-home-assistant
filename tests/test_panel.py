"""Tests for the authenticated Moonraker control panel."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker import MoonrakerGcodeUploadView
from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG
from custom_components.moonraker.panel import (
    PANEL_GCODE_URL,
    _relative_gcode_path,
    PANEL_CLIENT_URL,
    PANEL_EMBED_URL,
    PANEL_FRONTEND_PATH,
    PANEL_MODULE_URL,
    MoonrakerPanelActionView,
    MoonrakerPanelClientView,
    MoonrakerPanelDataView,
    MoonrakerPanelEmbedView,
    MoonrakerPanelGcodeView,
    MoonrakerPanelModuleView,
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
        sidebar_title="Moonraker Control",
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
        "async_send_data": AsyncMock(),
        "async_refresh_files": AsyncMock(),
        "async_fetch_data": AsyncMock(return_value={}),
        "async_add_listener": MagicMock(return_value=lambda: None),
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
        "power_devices": {"devices": [{"device": "led", "status": "on"}, "skip", {}]},
    }

    async def _boom():
        raise RuntimeError("webcams down")

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


async def _post_action(view, payload):
    request = SimpleNamespace()
    request.json = AsyncMock(return_value=payload)
    return await view.post(request)


def view_for(view, coordinator):
    """Point a view at a coordinator double."""
    view._resolve = MagicMock(return_value=coordinator)
    return view


async def test_action_view_request_handling(hass):
    """The action endpoint validates JSON, printers, and action failures."""
    view = MoonrakerPanelActionView(hass)

    request = SimpleNamespace()
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
    await hass.async_block_till_done()
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
    await hass.async_block_till_done()
    connection.send_result.assert_called_once_with(7)
    assert connection.send_message.called
    assert 7 in connection.subscriptions

    # A coordinator update fires the push task
    connection.send_message.reset_mock()
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert connection.send_message.called

    # A broken payload builder logs but never kills the subscription
    connection.send_message.reset_mock()
    with patch(
        "custom_components.moonraker.panel._panel_payload",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
    assert not connection.send_message.called
