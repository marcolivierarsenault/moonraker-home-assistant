"""Tests for the authenticated Moonraker control panel."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.moonraker import MoonrakerGcodeUploadView
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
    assert session.get.call_args.args[0].endswith("/server/files/gcodes/parts/active.gcode")
    assert session.get.call_args.kwargs["headers"] == {"X-Api-Key": "private-key"}
    assert stream_response.write.await_count == 2
    stream_response.write_eof.assert_awaited_once()
