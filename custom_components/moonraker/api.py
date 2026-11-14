"""moonraker Client."""

from asyncio import get_running_loop
from contextlib import suppress

from aiohttp import ClientError, ClientSession
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
        # Set by stop(), so a refresh still running during unload doesn't
        # reconnect. Unlike `running`, it isn't set before the first start().
        self.stopped = False
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
