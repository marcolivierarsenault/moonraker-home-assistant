"""API Tests."""

from unittest.mock import AsyncMock, patch

from custom_components.moonraker.api import MoonrakerApiClient


async def test_connect_client():
    """Test connect client."""
    with (
        patch("moonraker_api.MoonrakerClient"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.connect"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.disconnect"),
    ):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125, api_key="1dd2")
        assert not moonraker_api.running
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running


async def test_none_port_connect_client():
    """Test connect client."""
    with (
        patch("moonraker_api.MoonrakerClient"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.connect"),
        patch("moonraker_api.websockets.websocketclient.WebsocketClient.disconnect"),
    ):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125, api_key="1dd2")
        assert not moonraker_api.running
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running


async def test_disconnect_client():
    """Stop should disconnect the websocket client."""
    with patch("moonraker_api.MoonrakerClient"):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125, api_key="1dd2")
    moonraker_api.client.disconnect = AsyncMock()
    await moonraker_api.stop()
    moonraker_api.client.disconnect.assert_awaited_once()
    assert moonraker_api.running is False


async def test_notification_dispatch():
    """Notifications forward to the registered handler when present."""
    with patch("moonraker_api.MoonrakerClient"):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125, api_key="1dd2")

    # No handler registered -> no-op
    await moonraker_api.on_notification("notify_status_update", [])

    handler = AsyncMock()
    moonraker_api.notification_handler = handler
    await moonraker_api.on_notification("notify_status_update", [{"a": 1}])
    handler.assert_awaited_once_with("notify_status_update", [{"a": 1}])
