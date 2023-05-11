"""Sample ASYNC moonraker Client."""
import logging

from homeassistant.helpers.dispatcher import async_dispatcher_send
from moonraker_api import MoonrakerClient, MoonrakerListener

TIMEOUT = 10


_LOGGER = logging.getLogger(__name__)


class MoonrakerApiClient(MoonrakerListener):
    """Moonraker communication API"""

    def __init__(self, hass, url, session, port: int = 7125, api_key: str = None):
        self.running = False
        self.hass = hass
        if api_key == "":
            api_key = None
        if port is None:
            port = 7125
        self.client = MoonrakerClient(
            listener=self, host=url, port=port, session=session, api_key=api_key
        )

    async def state_changed(self, state: str) -> None:
        """Notifies of changing websocket state."""
        _LOGGER.warning("Stated changed to {%s}", state)
        if state == "ws_connected":
            await self._do_ready_handling()

    async def start(self) -> None:
        """Start the websocket connection."""
        self.running = True
        return await self.client.connect()

    async def stop(self) -> None:
        """Stop the websocket connection."""
        self.running = False
        await self.client.disconnect()

    async def on_notification(self, method: str, data) -> None:
        """Notifies of state updates."""

        if method == "notify_status_update":
            _LOGGER.warning("Received notification %s (%s)", method, data)
            message = data[0]
            timestamp = data[1]
            for module, state in message.items():
                async_dispatcher_send(self.hass, "THISISATEST", state)

    async def _do_ready_handling(self) -> None:
        """Set status as available and request subscriptions."""
        subscriptions = {"toolhead": ["position"]}
        supported_modules = await self.client.get_supported_modules()
        available = {
            key: val for key, val in subscriptions.items() if key in supported_modules
        }

        _LOGGER.info("Requesting subscriptions to printer state ()")
        aa = await self.client.call_method(
            "printer.objects.subscribe", objects=available
        )
