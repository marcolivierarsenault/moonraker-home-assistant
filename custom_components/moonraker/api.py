"""Sample ASYNC moonraker Client."""
import logging

from moonraker_api import MoonrakerClient, MoonrakerListener

TIMEOUT = 10


_LOGGER = logging.getLogger(__name__)


class MoonrakerApiClient(MoonrakerListener):
    """Moonraker communication API"""

    def __init__(self, url, session, port: int = 7125, api_key: str = None):
        self.running = False
        if api_key == "":
            api_key = None
        if port is None:
            port = 7125
        self.client = MoonrakerClient(
            listener=self, host=url, port=port, session=session, api_key=api_key
        )

    async def state_changed(self, state: str) -> None:
        """Notifies of changing websocket state."""
        _LOGGER.debug("Stated changed to {%s}", state)

    async def start(self) -> None:
        """Start the websocket connection."""
        self.running = True
        return await self.client.connect()

    async def stop(self) -> None:
        """Stop the websocket connection."""
        self.running = False
        await self.client.disconnect()
