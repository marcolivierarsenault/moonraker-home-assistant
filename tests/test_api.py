import pytest

from unittest.mock import patch

from custom_components.moonraker.api import MoonrakerApiClient


@pytest.fixture(name="bypass_moonrakerpy_client", autouse=True)
def bypass_moonrakerpy_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.api.MoonrakerPrinter"):
        yield


async def test_connect_client():
    client = MoonrakerApiClient("notaURL")
    client.connect_client()
    print(client.get_data())
    assert client._url == "notaURL"
