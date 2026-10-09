"""moonraker Client."""

from collections.abc import Awaitable, Callable
from typing import Any

from moonraker_api import MoonrakerClient, MoonrakerListener


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
        self._stopped = False
        self.notification_handler: Callable[[str, Any], Awaitable[None]] | None = (
            None
        )
        if api_key == "":
            api_key = None
        self.client = MoonrakerClient(
            listener=self,
            host=url,
            port=port,
            session=session,
            api_key=api_key,
            ssl=tls,
        )

    async def start(self) -> None:
        """Start the websocket connection."""
        self._stopped = False
        self.running = True
        await self.client.connect()

    async def stop(self) -> None:
        """Stop the websocket connection."""
        if self._stopped:
            return
        self.running = False
        await self.client.disconnect()
        self._stopped = True

    async def on_notification(self, method: str, data: Any) -> None:
        """Dispatch a Moonraker notification to the registered handler."""
        if self.notification_handler is not None:
            await self.notification_handler(method, data)
