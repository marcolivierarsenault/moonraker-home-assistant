"""Test how often the file details are fetched."""

from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from moonraker_api.const import WEBSOCKET_STATE_CONNECTED
from pytest_homeassistant.common import MockConfigEntry

from custom_components.moonraker import async_unload_entry
from custom_components.moonraker.const import (
    DOMAIN,
    METHODS,
    NOTIFY_FILELIST_CHANGED,
    NOTIFY_STATUS_UPDATE,
)

from .const import MOCK_CONFIG

METADATA = METHODS.SERVER_FILES_METADATA.value
QUERY = METHODS.PRINTER_OBJECTS_QUERY.value


ESTIMATE = "sensor.mainsail_slicer_print_duration_estimate"
HEIGHT = "sensor.mainsail_object_height"
FILENAME = "sensor.mainsail_filename"


def _state(hass, entity_id):
    return float(hass.states.get(entity_id).state)


class Printer:
    """Answer Moonraker calls and record them."""

    def __init__(self, response) -> None:
        """Init."""
        self.response = response
        self.status = response["status"]
        self.details = {"estimated_time": 3600, "object_height": 10.0}
        self.calls = []
        # Awaited after a call of this method was made, before its reply
        self.during = (None, None)
        self.fail = None

    async def call_method(self, method, **kwargs):
        """Answer a call."""
        self.calls.append((method, kwargs))
        if method == self.fail:
            raise ConnectionError
        result = self.response
        if method == METADATA:
            result = self.details
        elif method == QUERY:
            result = {
                **self.response,
                "status": dict(self.status),
            }
        if method == self.during[0]:
            await self.during[1]()
        return result

    def set_print(self, **values):
        """Change the print stats."""
        self.status["print_stats"] = {**self.status["print_stats"], **values}

    def files(self):
        """Return the files whose details were fetched."""
        return [
            kwargs["filename"] for method, kwargs in self.calls if method == METADATA
        ]


@pytest.fixture(name="printer")
def printer_fixture(get_default_api_response):
    """Connect to a printer that records the calls made."""
    printer = Printer(get_default_api_response)
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "moonraker_api.MoonrakerClient.call_method",
            side_effect=printer.call_method,
        ),
        patch(
            "moonraker_api.MoonrakerClient.is_connected",
            new_callable=PropertyMock,
            return_value=True,
        ),
    ):
        yield printer


@pytest.fixture(name="coordinator")
async def coordinator_fixture(hass, printer):
    """Set up the integration with a print running."""
    printer.set_print(state="printing", filename="a.gcode")
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_interval = None
    coordinator._unschedule_refresh()
    await coordinator.async_refresh()
    printer.calls.clear()
    yield coordinator
    printer.during = (None, None)
    printer.fail = None
    assert await async_unload_entry(hass, entry)


async def test_one_objects_query_per_update(hass, coordinator, printer):
    """An update queries the printer objects once and keeps the file details."""
    await coordinator.async_refresh()

    assert [method for method, _ in printer.calls].count(QUERY) == 1
    assert printer.files() == []
    assert _state(hass, ESTIMATE) == 1.0
    assert _state(hass, HEIGHT) == 10.0


async def test_new_file_fetches_details(hass, coordinator, printer):
    """Another file's details are fetched, and only the last file's are kept."""
    printer.set_print(filename="b.gcode")
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert printer.files() == ["b.gcode"]

    printer.set_print(filename="a.gcode")
    await coordinator.async_refresh()
    assert printer.files() == ["b.gcode", "a.gcode"]


async def test_incomplete_file_drops_earlier_details(hass, coordinator, printer):
    """Going back to the earlier file fetches its details again."""
    complete, printer.details = printer.details, {"size": 1}
    printer.set_print(filename="b.gcode")
    await coordinator.async_refresh()
    printer.details = {**complete, "estimated_time": 7200}
    printer.set_print(filename="a.gcode")
    await coordinator.async_refresh()

    assert printer.files() == ["b.gcode", "a.gcode"]
    assert _state(hass, ESTIMATE) == 2.0


async def test_no_file_drops_earlier_details(hass, coordinator, printer):
    """A file that comes back after no file was loaded is fetched again."""
    printer.status["virtual_sdcard"] = {"file_path": None}
    printer.set_print(filename="")
    await coordinator.async_refresh()
    printer.details = {"estimated_time": 7200}
    printer.set_print(filename="a.gcode")
    await coordinator.async_refresh()

    assert printer.files() == ["a.gcode"]
    assert _state(hass, ESTIMATE) == 2.0


async def test_virtual_sdcard_file_used(hass, coordinator, printer):
    """The file path is used when the print stats name no file."""
    printer.set_print(filename="")
    printer.status["virtual_sdcard"] = {"file_path": "gcodes/c.gcode"}
    await coordinator.async_refresh()

    assert printer.files() == ["c.gcode"]


async def test_no_file_clears_details(hass, coordinator, printer):
    """Details of the last file aren't shown once no file is loaded."""
    printer.set_print(filename="")
    printer.status["virtual_sdcard"] = {"file_path": None}
    await coordinator.async_refresh()

    assert printer.files() == []
    assert hass.states.get(HEIGHT).state == "unknown"


@pytest.mark.parametrize("state", ["paused", "complete", "standby"])
async def test_state_change_fetches_details(hass, coordinator, printer, state):
    """A state change seen by a poll fetches the details again."""
    printer.set_print(state=state)
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert printer.files() == ["a.gcode"]

    # The estimate is only shown while printing
    printer.set_print(state="printing")
    printer.details = {"estimated_time": 7200}
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert printer.files() == ["a.gcode"] * 2
    assert _state(hass, ESTIMATE) == 2.0


async def test_restart_between_polls_fetches_details(hass, coordinator, printer):
    """A print that ends and starts again between polls is noticed by its pushes."""
    with patch.object(coordinator, "async_request_refresh", new_callable=AsyncMock):
        for state in ("complete", "printing"):
            await coordinator.moonraker.on_notification(
                NOTIFY_STATUS_UPDATE, [{"print_stats": {"state": state}}, 1.0]
            )
        await hass.async_block_till_done(wait_background_tasks=True)
    await coordinator.async_refresh()

    assert printer.files() == ["a.gcode"]


async def test_changed_files_fetch_details(hass, coordinator, printer):
    """A file sliced again under the same name is noticed."""
    printer.details = {"estimated_time": 7200}
    await coordinator.moonraker.on_notification(
        NOTIFY_FILELIST_CHANGED, [{"action": "modify_file"}]
    )
    await coordinator.async_refresh()

    assert printer.files() == ["a.gcode"]
    assert _state(hass, ESTIMATE) == 2.0


async def test_reconnect_fetches_details(hass, coordinator, printer):
    """File changes can be missed while disconnected."""
    await coordinator.moonraker.state_changed(WEBSOCKET_STATE_CONNECTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    await coordinator.async_refresh()

    assert printer.files() == ["a.gcode"]


@pytest.mark.parametrize(
    "details",
    [{"error": {"message": "not found"}}, {"size": 1}, {"estimated_time": None}],
)
async def test_incomplete_details_are_fetched_again(
    hass, coordinator, printer, details
):
    """Details Moonraker hasn't read yet are fetched until they are there."""
    printer.set_print(filename="b.gcode")
    complete, printer.details = printer.details, details
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert printer.files() == ["b.gcode"] * 2

    printer.details = complete
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert printer.files() == ["b.gcode"] * 3
    assert _state(hass, ESTIMATE) == 1.0


async def test_zero_estimated_time_is_kept(hass, coordinator, printer):
    """Zero is a value, not missing data."""
    printer.set_print(filename="b.gcode")
    printer.details = {"estimated_time": 0}
    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert printer.files() == ["b.gcode"]
    assert _state(hass, ESTIMATE) == 0.0


async def test_change_while_fetching_is_not_lost(hass, coordinator, printer):
    """Details requested before a change are not kept."""
    printer.set_print(filename="b.gcode")

    async def change():
        await coordinator.moonraker.on_notification(NOTIFY_FILELIST_CHANGED, [{}])

    printer.during = (METADATA, change)
    await coordinator.async_refresh()
    printer.during = (None, None)
    printer.details = {"estimated_time": 10800}
    await coordinator.async_refresh()

    assert printer.files() == ["b.gcode"] * 2
    assert _state(hass, ESTIMATE) == 3.0


async def test_file_pushed_during_update_is_used(hass, coordinator, printer):
    """A file pushed while the objects query runs decides the details fetched."""

    async def push():
        await coordinator.moonraker.on_notification(
            NOTIFY_STATUS_UPDATE, [{"print_stats": {"filename": "b.gcode"}}, 1.0]
        )

    printer.during = (QUERY, push)
    await coordinator.async_refresh()

    assert printer.files() == ["b.gcode"]
    assert hass.states.get(FILENAME).state == "b.gcode"


async def test_failed_details_are_fetched_again(hass, coordinator, printer):
    """A failed request fails the update, as before, and is made again."""
    printer.set_print(filename="b.gcode")
    printer.fail = METADATA
    await coordinator.async_refresh()
    assert isinstance(coordinator.last_exception, UpdateFailed)

    printer.fail = None
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert printer.files() == ["b.gcode"] * 2
