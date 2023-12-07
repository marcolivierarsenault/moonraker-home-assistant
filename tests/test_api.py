"""API Tests."""
from unittest.mock import patch

from custom_components.moonraker.api import MoonrakerApiClient


async def test_connect_client():
    """Test connect client."""
    with patch("moonraker_api.MoonrakerClient"), patch(
        "moonraker_api.websockets.websocketclient.WebsocketClient.connect"
    ), patch("moonraker_api.websockets.websocketclient.WebsocketClient.disconnect"):
        moonraker_api = MoonrakerApiClient("notaURL", None, port="1234", api_key="1dd2")
        assert not moonraker_api.running
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running


async def test_none_port_connect_client():
    """Test connect client."""
    with patch("moonraker_api.MoonrakerClient"), patch(
        "moonraker_api.websockets.websocketclient.WebsocketClient.connect"
    ), patch("moonraker_api.websockets.websocketclient.WebsocketClient.disconnect"):
        moonraker_api = MoonrakerApiClient("notaURL", None, port=None, api_key="1dd2")
        assert not moonraker_api.running
        await moonraker_api.start()
        assert moonraker_api.running
        await moonraker_api.stop()
        assert not moonraker_api.running
