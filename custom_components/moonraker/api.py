"""moonraker Client."""

from asyncio import get_running_loop
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiohttp import ClientError, ClientSession
from moonraker_api import MoonrakerClient, MoonrakerListener
from moonraker_api.const import WEBSOCKET_STATE_CONNECTED


class MoonrakerApiClient(MoonrakerListener):
    """Moonraker communication API."""

    def __init__(
        self,
        url,
        session,
        port: int = 7125,
        api_key: str | None = None,
        tls: bool = False,
    ):
        """Init."""
        self.running = False
        # Set by stop(), so a refresh still running during unload doesn't
        # reconnect. Unlike `running`, it isn't set before the first start().
        self.stopped = False
        # Called with each websocket notification (method, params)
        self.notification_handler: Callable[[str, Any], Awaitable[None]] | None = None
        # Called each time the websocket connects
        self.connected_handler: Callable[[], None] | None = None
        if api_key == "":
            api_key = None
        self.client = MoonrakerClient(
            listener=self,
            host=url,
            port=port,
            loop=get_running_loop(),
            session=session,
            api_key=api_key,
            ssl=tls,
        )

    async def start(self) -> None:
        """Start the websocket connection."""
        self.running = True
        self.stopped = False
        await self.client.connect()

    async def stop(self) -> None:
        """Stop the websocket connection."""
        self.running = False
        self.stopped = True
        await self.client.disconnect()

    async def state_changed(self, state: str) -> None:
        """Tell the registered handler when the websocket connects."""
        if state == WEBSOCKET_STATE_CONNECTED and self.connected_handler is not None:
            self.connected_handler()

    async def on_notification(self, method: str, data: Any) -> None:
        """Pass a Moonraker notification to the registered handler."""
        if self.notification_handler is not None:
            await self.notification_handler(method, data)


async def async_fetch_api_key(
    session: ClientSession,
    host: str,
    port: int | str,
    tls: bool,
    username: str,
    password: str,
) -> str:
    """Log in to Moonraker and return its API key."""
    base_url = f"{'https' if tls else 'http'}://{host}:{port}"
    async with session.post(
        f"{base_url}/access/login",
        json={"username": username, "password": password, "source": "moonraker"},
    ) as response:
        response.raise_for_status()
        token = (await response.json())["result"]["token"]

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with session.get(
            f"{base_url}/access/api_key", headers=headers
        ) as response:
            response.raise_for_status()
            return (await response.json())["result"]
    finally:
        with suppress(ClientError):
            async with session.post(f"{base_url}/access/logout", headers=headers):
                pass
