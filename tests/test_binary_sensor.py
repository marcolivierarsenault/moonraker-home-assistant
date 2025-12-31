"""Binary_sensor Tests."""

from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moonraker.binary_sensor import (
    MoonrakerBinarySensor,
    MoonrakerBinarySensorDescription,
    update_available_fn,
)
from custom_components.moonraker.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


async def test_runout_filament_sensor_missing(hass, get_data, get_printer_objects_list):
    """Test."""
    get_data["status"].pop("filament_switch_sensor filament_sensor_1", None)
    get_data["status"].pop("filament_switch_sensor filament_sensor_2", None)
    get_printer_objects_list["objects"].remove(
        "filament_switch_sensor filament_sensor_1"
    )
    get_printer_objects_list["objects"].remove(
        "filament_switch_sensor filament_sensor_2"
    )

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state is None
    state = hass.states.get("binary_sensor.mainsail_filament_sensor_2")
    assert state is None


async def test_runout_filament_sensor(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state.state == "on"


async def test_multiple_runout_filament_sensor(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state.state == "on"

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_2")
    assert state.state == "on"


async def test_runout_filament_sensor_off(hass, get_data):
    """Test."""
    get_data["status"]["filament_switch_sensor filament_sensor_1"][
        "filament_detected"
    ] = False

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.mainsail_filament_sensor_1")
    assert state.state == "off"


async def test_update_available(hass):
    """Test update available."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert entity.disabled
    entity_registry.async_update_entity(
        "binary_sensor.mainsail_update_available",
        disabled_by=None,
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert not entity.disabled

    state = hass.states.get("binary_sensor.mainsail_update_available")
    assert state.state == "on"


async def test_update_available_system(hass, get_machine_update_status):
    """Test update available."""
    get_machine_update_status["version_info"]["crownest"]["version"] = "v4.1.1-1"
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert entity.disabled
    entity_registry.async_update_entity(
        "binary_sensor.mainsail_update_available",
        disabled_by=None,
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert not entity.disabled

    state = hass.states.get("binary_sensor.mainsail_update_available")
    assert state.state == "on"


async def test_update_available_component(hass, get_machine_update_status):
    """Test update available."""
    get_machine_update_status["version_info"]["system"]["package_count"] = 0
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert entity.disabled
    entity_registry.async_update_entity(
        "binary_sensor.mainsail_update_available",
        disabled_by=None,
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert not entity.disabled

    state = hass.states.get("binary_sensor.mainsail_update_available")
    assert state.state == "on"


async def test_update_available_no_update(hass, get_machine_update_status):
    """Test update available."""
    get_machine_update_status["version_info"]["system"]["package_count"] = 0
    get_machine_update_status["version_info"]["crownest"]["version"] = "v4.1.1-1"
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert entity.disabled
    entity_registry.async_update_entity(
        "binary_sensor.mainsail_update_available",
        disabled_by=None,
    )

    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = entity_registry.async_get("binary_sensor.mainsail_update_available")
    assert entity
    assert not entity.disabled

    state = hass.states.get("binary_sensor.mainsail_update_available")
    assert state.state == "off"


async def test_update_available_missing_machine_update(hass):
    """Test update available without machine_update data."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    coordinator.data.pop("machine_update", None)

    desc = MoonrakerBinarySensorDescription(
        key="update_available_direct",
        sensor_name="update_available",
        is_on_fn=update_available_fn,
        name="Update Available",
    )
    sensor = MoonrakerBinarySensor(coordinator, config_entry, desc)
    assert sensor.is_on is False


async def test_update_available_missing_remote_version(hass):
    """Test update available skips incomplete component data."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    coordinator.data["machine_update"] = {
        "version_info": {
            "system": {"package_count": 0},
            "klipper": "invalid",
            "mainsail": {"version": "v2.8.0"},
        }
    }

    desc = MoonrakerBinarySensorDescription(
        key="update_available_incomplete",
        sensor_name="update_available",
        is_on_fn=update_available_fn,
        name="Update Available",
    )
    sensor = MoonrakerBinarySensor(coordinator, config_entry, desc)
    assert sensor.is_on is False
