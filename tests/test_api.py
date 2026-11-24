"""API Tests."""

from unittest.mock import patch

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
        assert not moonraker_api.stopped
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running
        assert moonraker_api.stopped
        await moonraker_api.start()
        assert not moonraker_api.stopped


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


async def test_notification_handler():
    """Notifications go to the registered handler, if there is one."""
    with patch("moonraker_api.MoonrakerClient"):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125)
        # No handler yet: ignored
        await moonraker_api.on_notification("notify_status_update", [{}])

        received = []

        async def handler(method, params):
            received.append((method, params))

        moonraker_api.notification_handler = handler
        await moonraker_api.on_notification("notify_status_update", [{"a": 1}])

    assert received == [("notify_status_update", [{"a": 1}])]


async def test_connected_handler():
    """The connected handler runs when the websocket connects, and only then."""
    with patch("moonraker_api.MoonrakerClient"):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=7125)
        # No handler yet: ignored
        await moonraker_api.state_changed("ws_connected")

        calls = []
        moonraker_api.connected_handler = lambda: calls.append(True)
        await moonraker_api.state_changed("ws_connecting")
        await moonraker_api.state_changed("ws_connected")

    assert calls == [True]
