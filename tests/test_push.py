"""Test status updates pushed by Moonraker."""

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from moonraker_api.const import WEBSOCKET_STATE_CONNECTED
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.moonraker import (
    _is_measured_change,
    _merge_status,
    async_unload_entry,
)
from custom_components.moonraker.const import (
    DOMAIN,
    METHODS,
    NOTIFY_KLIPPY_READY,
    NOTIFY_STATUS_UPDATE,
    PUSH_UPDATE_INTERVAL,
)

from .const import MOCK_CONFIG

EXTRUDER = "sensor.mainsail_extruder_temperature"
EXTRUDER_TARGET = "number.mainsail_extruder_target"


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip connecting to Moonraker."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "custom_components.moonraker._async_is_tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


async def _setup(hass):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    # Pass on the subscription reply, and stop polling so a poll doesn't
    # replace pushed values while time moves on.
    coordinator._async_flush_push()
    coordinator.update_interval = None
    coordinator._unschedule_refresh()
    return config_entry, coordinator


def _subscribe_calls(call_method):
    return [
        call
        for call in call_method.call_args_list
        if call.args and call.args[0] == METHODS.PRINTER_OBJECTS_SUBSCRIBE.value
    ]


async def _push(coordinator, changes):
    await coordinator.moonraker.on_notification(NOTIFY_STATUS_UPDATE, [changes, 1234.5])


def _later(hass, seconds):
    async_fire_time_changed(
        hass, dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
    )


def test_merge_status():
    """Changed fields are merged into objects; other values are replaced."""
    status = {"extruder": {"temperature": 20.0, "target": 0.0}, "list": [1]}
    merged = _merge_status(
        status, {"extruder": {"temperature": 25.0}, "list": [2], "new": {"a": 1}}
    )
    assert merged == {
        "extruder": {"temperature": 25.0, "target": 0.0},
        "list": [2],
        "new": {"a": 1},
    }
    # The original is left alone
    assert status["extruder"]["temperature"] == 20.0


async def test_subscribes_after_setup(hass, get_default_api_response):
    """Every queried object is subscribed to once the platforms are set up."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value=get_default_api_response,
    ) as call_method:
        config_entry, coordinator = await _setup(hass)

    calls = _subscribe_calls(call_method)
    assert len(calls) == 1
    assert calls[0].kwargs["objects"] == coordinator.query_obj["objects"]
    # The extruder number platform's target field is in the subscription
    assert "target" in calls[0].kwargs["objects"]["extruder"]
    assert coordinator._subscribed
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("changes", "measured"),
    [
        ({"extruder": {"temperature": 1.0, "power": 0.5}}, True),
        ({"gcode_move": {"speed": 1500}, "toolhead": {"position": [1, 2]}}, True),
        ({"extruder": {"temperature": 1.0, "target": 200.0}}, False),
        ({"fan": {"speed": 0.5}}, False),
        ({"temperature_fan fan_temp": {"speed": 0.4, "temperature": 30.0}}, True),
        ({"temperature_fan fan_temp": {"target": 40.0}}, False),
        ({"hall_filament_width_sensor": {"Diameter": 1.74, "Raw": 3000}}, True),
        ({"heater_fan hotend_fan": {"speed": 1.0}}, True),
        ({"controller_fan board_fan": {"speed": 0.5}}, True),
        ({"webhooks": "not a dict"}, False),
    ],
)
def test_is_measured_change(changes, measured):
    """Only changes to always-changing readings count as measured."""
    assert _is_measured_change(changes) is measured


async def test_setting_push_updates_entities_after_interval(hass):
    """A pushed setting change reaches entities within the push interval."""
    config_entry, coordinator = await _setup(hass)
    assert hass.states.get(EXTRUDER).state == "205.02"

    await _push(coordinator, {"extruder": {"temperature": 123.4}})
    await _push(coordinator, {"extruder": {"target": 150.0, "temperature": 150.5}})
    # Merged straight away, other fields of the object kept
    assert coordinator.data["status"]["extruder"]["temperature"] == 150.5
    assert "power" in coordinator.data["status"]["extruder"]
    assert hass.states.get(EXTRUDER).state == "205.02"

    _later(hass, PUSH_UPDATE_INTERVAL)
    await hass.async_block_till_done()
    assert hass.states.get(EXTRUDER_TARGET).state == "150.0"
    assert hass.states.get(EXTRUDER).state == "150.5"
    assert await async_unload_entry(hass, config_entry)


async def test_reading_push_waits_for_poll(hass):
    """A pushed reading alone is merged but doesn't update entities."""
    config_entry, coordinator = await _setup(hass)

    await _push(coordinator, {"extruder": {"temperature": 123.4}})

    assert coordinator.data["status"]["extruder"]["temperature"] == 123.4
    assert coordinator._push_flush_unsub is None
    _later(hass, PUSH_UPDATE_INTERVAL)
    await hass.async_block_till_done()
    assert hass.states.get(EXTRUDER).state == "205.02"
    assert await async_unload_entry(hass, config_entry)


async def test_print_state_change_updates_now(hass):
    """A pushed print state change updates entities and runs a full update."""
    config_entry, coordinator = await _setup(hass)

    with patch.object(
        coordinator, "async_request_refresh", new_callable=AsyncMock
    ) as refresh:
        await _push(
            coordinator,
            {"print_stats": {"state": "paused"}, "extruder": {"temperature": 99.0}},
        )
        await hass.async_block_till_done()

    refresh.assert_awaited_once()
    assert hass.states.get(EXTRUDER).state == "99.0"
    assert coordinator._push_flush_unsub is None
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("notify_proc_stat_update", [{"cpu_temp": 40}]),
        (NOTIFY_STATUS_UPDATE, None),
        (NOTIFY_STATUS_UPDATE, []),
        (NOTIFY_STATUS_UPDATE, [{}, 1.0]),
        (NOTIFY_STATUS_UPDATE, ["not a dict", 1.0]),
    ],
)
async def test_other_notifications_ignored(hass, method, params):
    """Other notifications and empty updates change nothing."""
    config_entry, coordinator = await _setup(hass)
    data = coordinator.data

    await coordinator.moonraker.on_notification(method, params)

    assert coordinator.data is data
    assert coordinator._push_flush_unsub is None
    assert await async_unload_entry(hass, config_entry)


async def test_push_before_first_update_ignored(hass):
    """A push that arrives before any data exists is ignored."""
    config_entry, coordinator = await _setup(hass)
    coordinator.data = None

    await _push(coordinator, {"extruder": {"temperature": 1.0}})

    assert coordinator.data is None
    coordinator.data = {"status": {}}
    assert await async_unload_entry(hass, config_entry)


async def test_klippy_ready_resubscribes(hass, get_default_api_response):
    """Moonraker drops subscriptions when Klippy restarts, so subscribe again."""
    config_entry, coordinator = await _setup(hass)

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value=get_default_api_response,
    ) as call_method:
        await coordinator.moonraker.on_notification(NOTIFY_KLIPPY_READY, None)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert len(_subscribe_calls(call_method)) == 1
    assert await async_unload_entry(hass, config_entry)


async def test_klippy_ready_before_subscription(hass):
    """Klippy becoming ready before setup subscribed does nothing."""
    config_entry, coordinator = await _setup(hass)
    coordinator._push_wanted = False

    with patch.object(coordinator, "async_subscribe") as subscribe:
        await coordinator.moonraker.on_notification(NOTIFY_KLIPPY_READY, None)

    subscribe.assert_not_called()
    assert await async_unload_entry(hass, config_entry)


async def test_reconnect_resubscribes(hass):
    """A new websocket connection subscribes again."""
    config_entry, coordinator = await _setup(hass)

    with patch.object(
        coordinator, "async_subscribe", new_callable=AsyncMock
    ) as subscribe:
        await coordinator.moonraker.state_changed(WEBSOCKET_STATE_CONNECTED)
        await coordinator.moonraker.state_changed("ws_stopped")
        await hass.async_block_till_done(wait_background_tasks=True)

    subscribe.assert_awaited_once()
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    "result",
    [UpdateFailed("down"), {"error": {"message": "Klippy Host not connected"}}],
)
async def test_subscribe_failure(hass, result):
    """A failed subscription is left for the next Klippy ready."""
    config_entry, coordinator = await _setup(hass)
    data = coordinator.data
    coordinator._push_wanted = False

    kwargs = (
        {"side_effect": result}
        if isinstance(result, Exception)
        else {"return_value": result}
    )
    with patch.object(coordinator, "_async_fetch_data", **kwargs):
        await coordinator.async_subscribe()

    assert coordinator._push_wanted
    assert not coordinator._subscribed
    assert coordinator.data is data
    assert await async_unload_entry(hass, config_entry)


@pytest.mark.parametrize(
    "during", [METHODS.PRINTER_OBJECTS_QUERY.value, METHODS.PRINTER_INFO.value]
)
async def test_push_during_full_update_is_kept(hass, get_default_api_response, during):
    """A change pushed while a full update runs isn't overwritten by it."""
    config_entry, coordinator = await _setup(hass)

    async def call_method(method, **kwargs):
        if method == during:
            # Handled before the update applies its older query result
            await _push(coordinator, {"extruder": {"temperature": 222.0}})
        return get_default_api_response

    with (
        patch("moonraker_api.MoonrakerClient.call_method", side_effect=call_method),
        patch(
            "moonraker_api.MoonrakerClient.is_connected",
            new_callable=PropertyMock,
            return_value=True,
        ),
    ):
        await coordinator.async_refresh()

    assert coordinator.data["status"]["extruder"]["temperature"] == 222.0
    assert coordinator._pushed_since_query is None
    assert await async_unload_entry(hass, config_entry)


async def test_failed_full_update_clears_kept_pushes(hass):
    """Pushes kept for an update that fails are dropped with it."""
    config_entry, coordinator = await _setup(hass)

    async def fail():
        coordinator._pushed_since_query = {"extruder": {"temperature": 1.0}}
        raise UpdateFailed("down")

    with (
        patch.object(coordinator, "_async_fetch_all_data", side_effect=fail),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    assert coordinator._pushed_since_query is None
    assert await async_unload_entry(hass, config_entry)


async def test_unload_stops_push(hass):
    """Unloading drops the handler and any pending entity update."""
    config_entry, coordinator = await _setup(hass)
    await _push(coordinator, {"extruder": {"target": 123.0}})
    assert coordinator._push_flush_unsub is not None

    assert await hass.config_entries.async_unload(config_entry.entry_id)

    assert coordinator.moonraker.notification_handler is None
    assert coordinator.moonraker.connected_handler is None
    assert coordinator._push_flush_unsub is None
    assert not coordinator._push_wanted


@pytest.mark.parametrize("subscribed", [False, True])
async def test_poll_retries_failed_subscription(hass, subscribed):
    """A successful poll subscribes again if the subscription failed."""
    config_entry, coordinator = await _setup(hass)
    coordinator._subscribed = subscribed

    with patch.object(
        coordinator, "async_subscribe", new_callable=AsyncMock
    ) as subscribe:
        await coordinator.async_refresh()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert subscribe.await_count == (0 if subscribed else 1)
    assert await async_unload_entry(hass, config_entry)


async def test_one_subscription_at_a_time(hass):
    """A resubscribe waits for one already running instead of starting another."""
    config_entry, coordinator = await _setup(hass)
    release = asyncio.Event()
    calls = 0

    async def slow_subscribe():
        nonlocal calls
        calls += 1
        await release.wait()

    with patch.object(coordinator, "async_subscribe", side_effect=slow_subscribe):
        await coordinator.moonraker.on_notification(NOTIFY_KLIPPY_READY, None)
        await asyncio.sleep(0)
        await coordinator.moonraker.state_changed(WEBSOCKET_STATE_CONNECTED)
        await asyncio.sleep(0)
        release.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert calls == 1
    assert await async_unload_entry(hass, config_entry)


async def test_push_during_subscribe_is_kept(hass, get_default_api_response):
    """A change pushed while a subscribe request runs is applied on its reply."""
    config_entry, coordinator = await _setup(hass)

    async def call_method(method, **kwargs):
        await _push(coordinator, {"extruder": {"temperature": 222.0}})
        return get_default_api_response

    with patch("moonraker_api.MoonrakerClient.call_method", side_effect=call_method):
        await coordinator.async_subscribe()

    assert coordinator.data["status"]["extruder"]["temperature"] == 222.0
    assert coordinator._pushed_since_subscribe is None
    assert await async_unload_entry(hass, config_entry)


async def test_setup_subscription_is_tracked(hass):
    """The setup subscription counts as the one running, so a retry waits."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    release = asyncio.Event()
    calls = 0

    async def slow_subscribe(self):
        nonlocal calls
        calls += 1
        await release.wait()

    with patch(
        "custom_components.moonraker.MoonrakerDataUpdateCoordinator.async_subscribe",
        slow_subscribe,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        await asyncio.sleep(0)
        coordinator._async_resubscribe()
        release.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert calls == 1
    assert await async_unload_entry(hass, config_entry)
