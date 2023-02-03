"""Sample ASYNC moonraker Client."""
import logging


from moonraker_api import MoonrakerListener, MoonrakerClient

TIMEOUT = 10


_LOGGER = logging.getLogger(__name__)


class MoonrakerApiClient(MoonrakerListener):
    """Moonraker communication API"""

    def __init__(self, url, session):
        self.running = False
        self.client = MoonrakerClient(listener=self, host=url, session=session)

    async def state_changed(self, state: str) -> None:
        """Notifies of changing websocket state."""
        _LOGGER.debug(f"Stated changed to {state}")

    async def start(self) -> None:
        """Start the websocket connection."""
        self.running = True
        return await self.client.connect()

    async def stop(self) -> None:
        """Stop the websocket connection."""
        self.running = False
        await self.client.disconnect()
