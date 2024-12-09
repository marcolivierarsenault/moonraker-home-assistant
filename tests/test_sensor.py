"""Test moonraker sensor."""

import datetime as dt
from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
import pytest
from homeassistant.helpers.entity_registry import async_get as get_entity_registry
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.moonraker.const import DOMAIN, PRINTSTATES
from custom_components.moonraker.sensor import (
    calculate_current_layer,
    calculate_pct_job,
)

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client", autouse=True)
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


@pytest.fixture(name="data_for_calculate_pct")
def data_for_calculate_pct_fixture():
    """data_for_calculate_pct."""
    return {
        "estimated_time": 10,
        "status": {
            "print_stats": {"print_duration": 6, "filament_used": 1},
            "display_status": {"progress": 0.60},
        },
        "filament_total": 2,
    }


async def test_sensor_services_update(hass, get_data):
    """Test sensor services."""
    # Create a mock entry so we don't have to go through config flow

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_bed_target")

    assert state.state == "60.0"

    get_data["status"]["heater_bed"]["target"] = 100.0

    async_fire_time_changed(
        hass,
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mainsail_bed_target").state == "100.0"


"""test all sensors"""


@pytest.mark.parametrize(
    "sensor, value",
    [
        ("mainsail_mcu_temp", "32.43"),
        ("mainsail_eddy_temp", "32.43"),
        ("mainsail_bed_target", "60.0"),
        ("mainsail_bed_temperature", "60.01"),
        ("mainsail_extruder_target", "205.0"),
        ("mainsail_extruder_temperature", "205.02"),
        ("mainsail_extruder1_target", "220.0"),
        ("mainsail_extruder1_temperature", "220.01"),
        ("mainsail_progress", "90"),
        ("mainsail_printer_state", "ready"),
        ("mainsail_filename", "CE3E3V2_picture_frame_holder.gcode"),
        ("mainsail_current_display_message", "Custom Message"),
        ("mainsail_printer_message", "Printer is ready"),
        ("mainsail_current_print_state", "printing"),
        ("mainsail_current_print_message", ""),
        ("mainsail_print_projected_total_duration", "9197.46"),
        ("mainsail_print_time_left", "1182.94"),
        ("mainsail_print_duration", "133.58"),
        ("mainsail_filament_used", "5.0"),
        ("mainsail_progress", "90"),
        ("mainsail_bed_power", "26"),
        ("mainsail_extruder_power", "66"),
        ("mainsail_fan_speed", "51.23"),
        ("mainsail_fan_temp", "32.43"),
        ("mainsail_tmc2240_stepper_x_temp", "32.43"),
        ("mainsail_bme280_temp", "32.43"),
        ("mainsail_htu21d_temp", "32.43"),
        ("mainsail_lm75_temp", "32.43"),
        ("mainsail_heater_fan", "51.23"),
        ("mainsail_controller_fan", "51.23"),
        ("mainsail_nevermore_fan", "12.34"),
        ("mainsail_totals_print_time", "3h 9m 9s"),
        ("mainsail_totals_jobs", "3"),
        ("mainsail_totals_filament_used", "11.62"),
        ("mainsail_longest_print", "3h 9m 9s"),
        ("mainsail_total_layer", "33"),
        ("mainsail_current_layer", "22"),
        ("mainsail_toolhead_position_x", "23.3"),
        ("mainsail_toolhead_position_y", "22.2"),
        ("mainsail_toolhead_position_z", "10.2"),
        ("mainsail_slicer_print_duration_estimate", "8232.0"),
        ("mainsail_object_height", "62.6"),
        ("mainsail_speed_factor", "200.0"),
        ("mainsail_my_super_heater_temperature", "32.43"),
        ("mainsail_my_super_heater_target", "32.0"),
        ("mainsail_my_super_heater_power", "12"),
    ],
)
async def test_sensors(
    hass,
    sensor,
    value,
):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(f"sensor.{sensor}").state == value


# test all sensors
@pytest.mark.parametrize(
    "sensor, value",
    [
        ("mainsail_machine_update_system", "8 packages can be upgraded"),
        ("mainsail_version_crownest", "v4.0.4-6 > v4.1.1-1"),
        ("mainsail_version_mainsail", "v2.8.0"),
    ],
)
async def test_disabled_sensors(
    hass,
    sensor,
    value,
):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get(f"sensor.{sensor}")
    assert entity
    assert entity.disabled
    entity_registry.async_update_entity(
        f"sensor.{sensor}",
        disabled_by=None,
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = entity_registry.async_get(f"sensor.{sensor}")
    assert entity
    assert not entity.disabled

    state = hass.states.get(f"sensor.{sensor}")
    assert state.state == value


# test sensor affected by not printing state
@pytest.mark.parametrize(
    "sensor_not_printing, value",
    [
        ("mainsail_filename", ""),
        ("mainsail_current_print_state", "standby"),
        ("mainsail_filament_used", "0.0"),
        ("mainsail_print_duration", "0.0"),
        ("mainsail_print_time_left", "0.0"),
        ("mainsail_print_projected_total_duration", "0.0"),
        ("mainsail_progress", "0.0"),
        ("mainsail_total_layer", "0.0"),
        ("mainsail_current_layer", "0"),
    ],
)
async def test_sensors_not_printing(
    hass,
    sensor_not_printing,
    value,
    get_data,
):
    """Test."""
    get_data["status"]["print_stats"]["state"] = PRINTSTATES.STANDBY.value
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(f"sensor.{sensor_not_printing}").state == value


async def test_opt_sensor_missing(hass, get_data, get_printer_objects_list):
    """Test."""
    get_data["status"].pop("temperature_sensor mcu_temp", None)
    get_printer_objects_list["objects"].remove("temperature_sensor mcu_temp")

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_mcu_temp")
    assert state is None


async def test_opt_probe_missing(hass, get_data, get_printer_objects_list):
    """Test."""
    get_data["status"].pop("temperature_probe eddy_temp", None)
    get_printer_objects_list["objects"].remove("temperature_probe eddy_temp")

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_eddy_temp")
    assert state is None


async def test_eta(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_eta")

    assert dt.datetime.strptime(state.state, "%Y-%m-%dT%H:%M:%S%z") < dt.datetime.now(
        dt.timezone.utc
    ) + dt.timedelta(0, 1182.94 + 2)
    assert dt.datetime.strptime(state.state, "%Y-%m-%dT%H:%M:%S%z") > dt.datetime.now(
        dt.timezone.utc
    ) + dt.timedelta(0, 1182.94 - 2)


async def test_slicer_time_left(hass, get_data):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_slicer_print_time_left_estimate")

    target = str(
        round(
            get_data["estimated_time"]
            - get_data["status"]["print_stats"]["print_duration"],
            12,
        )
    )
    assert state.state == target


async def test_eta_no_current_data(hass, get_data):
    """Test."""
    get_data["status"]["print_stats"]["print_duration"] = 0

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_eta")

    assert state.state == "unknown"


async def test_calculate_pct_job(data_for_calculate_pct):
    """Test."""
    assert calculate_pct_job(data_for_calculate_pct) == 0.55


async def test_calculate_pct_job_no_time(data_for_calculate_pct):
    """Test."""
    data_for_calculate_pct["estimated_time"] = 0
    assert calculate_pct_job(data_for_calculate_pct) == 0.5


async def test_calculate_pct_job_no_filament(data_for_calculate_pct):
    """Test."""
    data_for_calculate_pct["filament_total"] = 0
    assert calculate_pct_job(data_for_calculate_pct) == 0.6


async def test_calculate_pct_job_no_filament_no_time(data_for_calculate_pct):
    """test_calculate_pct_job_no_filament_no_time."""

    data_for_calculate_pct["filament_total"] = 0
    data_for_calculate_pct["estimated_time"] = 0
    assert calculate_pct_job(data_for_calculate_pct) == 0


async def test_no_history_data(
    hass,
    get_data,
    get_printer_info,
    get_printer_objects_list,
    get_camera_info,
    get_gcode_help,
):
    """Test no history."""

    get_history = {"error": "method not found"}

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={
            **get_data,
            **get_printer_info,
            **get_printer_objects_list,
            **get_history,
            **get_camera_info,
            **get_gcode_help,
        },
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_totals_jobs")
    assert state is None


async def test_double_sensor_data(hass, get_data, get_printer_objects_list):
    """Test."""
    get_printer_objects_list["objects"].append("heater_fan controller_fan")
    get_data["status"]["heater_fan controller_fan"] = {"speed": 0.1234}

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = get_entity_registry(hass)

    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, "test_controller_fan_controller_fan"
        )
        is not None
    )

    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "test_heater_fan_controller_fan")
        is not None
    )


async def test_no_fan_sensor(hass, get_data, get_printer_objects_list):
    """Test."""
    get_data["status"].pop("fan")
    get_printer_objects_list["objects"].remove("fan")

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_fan")
    assert state is None


async def test_multi_mcu_sensor_data(hass, get_data, get_printer_objects_list):
    """Test."""
    get_printer_objects_list["objects"].append("mcu Extruder")
    get_data["status"]["mcu Extruder"] = {
        "last_stats": {
            "mcu_awake": 0.031,
            "mcu_task_avg": 0.000002,
            "mcu_task_stddev": 0.000012,
        },
    }

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = get_entity_registry(hass)

    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "test_mcu_Extruder_load")
        is not None
    )

    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "test_mcu_Extruder_awake")
        is not None
    )


async def test_multi_mcu_sensor_missing_data(hass, get_data, get_printer_objects_list):
    """Test."""
    get_printer_objects_list["objects"].append("mcu Extruder")
    get_data["status"]["mcu Extruder"] = {
        "last_stats": None,
    }

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = get_entity_registry(hass)

    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "test_mcu_Extruder_load")
        is not None
    )

    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "test_mcu_Extruder_awake")
        is not None
    )


async def test_rounding_fan(hass, get_data):
    """Test."""
    get_data["status"]["fan"]["speed"] = 0.33333333333

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_fan_speed")
    assert state.state == "33.33"


async def test_current_layer_not_in_info(hass, get_data):
    """Test."""
    get_data["status"]["print_stats"]["info"].pop("current_layer")

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_current_layer")
    assert state.state == "51"


async def test_total_layer_not_in_info(hass, get_data):
    """Test."""
    get_data["status"]["print_stats"]["info"].pop("total_layer")

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_total_layer")
    assert state.state == "313"


async def test_total_layer_info_is_none(hass, get_data):
    """Test."""
    get_data["status"]["print_stats"]["info"] = None

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_total_layer")
    assert state.state == "313"


async def test_total_layer_in_info_0(hass, get_data):
    """Test."""
    get_data["status"]["print_stats"]["info"]["total_layer"] = 0

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_total_layer")
    assert state.state == "313"


async def test_total_layer_in_info_is_none(hass, get_data):
    """Test."""
    get_data["status"]["print_stats"]["info"]["total_layer"] = None

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_total_layer")
    assert state.state == "313"


async def test_current_layer_calculated():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_calculated_layer_height_0():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0,
    }
    assert calculate_current_layer(data) == 0


async def test_current_layer_calculate_missing_layer_height():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 0


async def test_current_layer_calculated_partial_info():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "info": {},
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_update_no_system_update(hass, get_machine_update_status):
    """Test update available."""
    del get_machine_update_status["version_info"]["system"]

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("sensor.mainsail_machine_update_system")
    assert entity is None


async def test_update_no_info_item(hass, get_machine_update_status):
    """Test update available."""
    get_machine_update_status["version_info"]["mainsail"] = {}

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("sensor.mainsail_version_mainsail")
    assert entity is None

    entity = entity_registry.async_get("sensor.mainsail_machine_update_system")
    assert entity is not None
