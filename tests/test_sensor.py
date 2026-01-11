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
    _get_progress_value,
    calculate_current_layer,
    calculate_pct_job,
    calculate_print_progress,
    calculate_total_layer,
    format_idle_timeout_state,
)

from .const import MOCK_CONFIG

DEFAULT_VALUES = [
    ("mainsail_mcu_temp", "32.43"),
    ("mainsail_eddy_temp", "32.43"),
    ("mainsail_bed_temperature", "60.01"),
    ("mainsail_extruder_temperature", "205.02"),
    ("mainsail_extruder1_temperature", "220.01"),
    ("mainsail_progress", "90.7810423766328"),
    ("mainsail_print_speed", "123.46"),
    ("mainsail_printer_state", "ready"),
    ("mainsail_idle_timeout_state", "Ready"),
    ("mainsail_filename", "CE3E3V2_picture_frame_holder.gcode"),
    ("mainsail_current_display_message", "Custom Message"),
    ("mainsail_printer_message", "Printer is ready"),
    ("mainsail_current_print_state", "printing"),
    ("mainsail_current_print_message", ""),
    ("mainsail_print_projected_total_duration", "2.55485108570028"),
    ("mainsail_print_time_left", "0.328593266620827"),
    ("mainsail_print_duration", "133.575469144767"),
    ("mainsail_filament_used", "5.0"),
    ("mainsail_progress", "90.7810423766328"),
    ("mainsail_bed_power", "26.0537452725334"),
    ("mainsail_extruder_power", "66.6710806392505"),
    ("mainsail_fan_rpm", "3000.12321"),
    ("mainsail_fan_temp", "32.43"),
    ("mainsail_tmc2240_stepper_x_temp", "32.43"),
    ("mainsail_bme280_temp", "32.43"),
    ("mainsail_htu21d_temp", "32.43"),
    ("mainsail_lm75_temp", "32.43"),
    ("mainsail_heater_fan", "51.23"),
    ("mainsail_controller_fan", "51.23"),
    ("mainsail_controller_fan_rpm", "5000.32123"),
    ("mainsail_nevermore_fan", "12.34"),
    ("mainsail_totals_print_time", "3h 9m 9s"),
    ("mainsail_totals_jobs", "3"),
    ("mainsail_totals_filament_used", "11.615718840002"),
    ("mainsail_longest_print", "3h 9m 9s"),
    ("mainsail_total_layer", "33"),
    ("mainsail_current_layer", "22"),
    ("mainsail_toolhead_position_x", "23.30234"),
    ("mainsail_toolhead_position_y", "22.20234"),
    ("mainsail_toolhead_position_z", "10.20234"),
    ("mainsail_slicer_print_duration_estimate", "2.28666666666667"),
    ("mainsail_object_height", "62.6"),
    ("mainsail_my_super_heater_temperature", "32.43"),
    ("mainsail_my_super_heater_power", "12.34"),
    ("mainsail_mixed_case_temperature", "33.21"),
    ("mainsail_mixed_case_power", "45.67"),
]


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

    state = hass.states.get("sensor.mainsail_bed_temperature")

    assert state.state == "60.01"

    get_data["status"]["heater_bed"]["temperature"] = 100.0

    async_fire_time_changed(
        hass,
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mainsail_bed_temperature").state == "100.0"


"""test all sensors"""


async def test_sensors(hass):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    for sensor, value in DEFAULT_VALUES:
        assert hass.states.get(f"sensor.{sensor}").state == value

    assert hass.states.get("sensor.mainsail_my_super_heater_target") is None
    assert hass.states.get("sensor.mainsail_mixed_case_target") is None


async def test_idle_timeout_state_normalized(hass, get_data):
    """Idle timeout state should be title-cased regardless of source casing."""
    get_data["status"]["idle_timeout"]["state"] = "standby"

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_idle_timeout_state")
    assert state.state == "Standby"


async def test_idle_timeout_state_complete(hass, get_data):
    """Idle timeout state should accept completed prints."""
    get_data["status"]["idle_timeout"]["state"] = "complete"

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_idle_timeout_state")
    assert state.state == "Complete"
    assert "Complete" in state.attributes["options"]


def test_idle_timeout_state_handles_missing():
    """format_idle_timeout_state returns None when state missing."""
    data = {"status": {"idle_timeout": {}}}
    assert format_idle_timeout_state(data) is None


def test_idle_timeout_state_non_string_returns_none():
    """format_idle_timeout_state returns None for non-string states."""
    data = {"status": {"idle_timeout": {"state": 5}}}
    assert format_idle_timeout_state(data) is None


def test_idle_timeout_state_unknown_returns_none():
    """format_idle_timeout_state returns None for unsupported states."""
    data = {"status": {"idle_timeout": {"state": "mystery_mode"}}}
    assert format_idle_timeout_state(data) is None


def test_idle_timeout_state_blank_returns_none():
    """format_idle_timeout_state returns None for blank values."""
    data = {"status": {"idle_timeout": {"state": "   "}}}
    assert format_idle_timeout_state(data) is None


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
        ("mainsail_print_speed", "0.0"),
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


async def test_print_speed_missing_speed(hass, get_data):
    """Print speed sensor reports unknown when data missing while printing."""

    get_data["status"]["gcode_move"].pop("speed", None)
    get_data["status"].pop("motion_report", None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_speed")
    assert state.state == "unknown"


async def test_print_speed_preheating(hass, get_data):
    """Print speed reports 0 while heating before motion starts."""

    get_data["status"]["toolhead"]["print_time"] = 0.0
    get_data["status"]["motion_report"]["live_velocity"] = 0.0

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_speed")
    assert state.state == "0.0"


async def test_print_speed_without_motion_report(hass, get_data):
    """Fallback to gcode_move speed when motion_report is unavailable."""

    get_data["status"].pop("motion_report", None)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_print_speed")
    assert state.state == "123.46"


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

    # ETA is rounded to nearest minute, so allow ±30 seconds tolerance
    assert dt.datetime.strptime(state.state, "%Y-%m-%dT%H:%M:%S%z") < dt.datetime.now(
        dt.timezone.utc
    ) + dt.timedelta(0, 1182.94 + 30)
    assert dt.datetime.strptime(state.state, "%Y-%m-%dT%H:%M:%S%z") > dt.datetime.now(
        dt.timezone.utc
    ) + dt.timedelta(0, 1182.94 - 30)


async def test_slicer_time_left(hass, get_data):
    """Test."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_slicer_print_time_left_estimate")

    target = (
        get_data["estimated_time"] - get_data["status"]["print_stats"]["print_duration"]
    ) / 3600
    assert state.state == f"{target:.15f}"


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
    assert calculate_pct_job(data_for_calculate_pct) == 0.6


async def test_calculate_pct_job_missing_progress(data_for_calculate_pct):
    """Progress defaults to 0 when missing."""
    data_for_calculate_pct["status"]["display_status"]["progress"] = None

    assert calculate_pct_job(data_for_calculate_pct) == 0.25


async def test_calculate_print_progress_file_relative():
    """File-relative progress should use gcode byte offsets."""
    data = {
        "gcode_start_byte": 100,
        "gcode_end_byte": 1100,
        "status": {
            "print_stats": {"filename": "test.gcode"},
            "virtual_sdcard": {"file_position": 600, "progress": 0.2},
            "display_status": {"progress": 0.3},
        },
    }

    assert calculate_print_progress(data) == pytest.approx(0.5)


async def test_calculate_print_progress_file_relative_bounds():
    """File-relative progress should clamp to start/end bounds."""
    data = {
        "gcode_start_byte": 100,
        "gcode_end_byte": 1100,
        "status": {
            "print_stats": {"filename": "test.gcode"},
            "virtual_sdcard": {"file_position": 100, "progress": 0.2},
        },
    }

    assert calculate_print_progress(data) == 0.0

    data["status"]["virtual_sdcard"]["file_position"] = 1100
    assert calculate_print_progress(data) == 1.0


async def test_calculate_print_progress_fallback_display_status():
    """Fallback to display_status when file-relative progress isn't available."""
    data = {"status": {"display_status": {"progress": 0.6}}}

    assert calculate_print_progress(data) == pytest.approx(0.6)


async def test_get_progress_value_invalid_status():
    """Invalid status should return no progress."""
    assert _get_progress_value([]) is None


async def test_calculate_print_progress_no_progress_values():
    """Missing progress values should return 0."""
    data = {
        "status": {
            "print_stats": {"filename": "test.gcode"},
            "display_status": {"progress": None},
            "virtual_sdcard": {"progress": None},
        }
    }

    assert calculate_print_progress(data) == 0.0


async def test_calculate_print_progress_invalid_bytes_fallback():
    """Invalid gcode byte offsets should fall back to display_status."""
    data = {
        "gcode_start_byte": "bad",
        "gcode_end_byte": "data",
        "status": {
            "print_stats": {"filename": "test.gcode"},
            "display_status": {"progress": 0.25},
            "virtual_sdcard": {"file_position": 200},
        },
    }

    assert calculate_print_progress(data) == pytest.approx(0.25)


async def test_calculate_print_progress_null_bytes():
    """Null gcode byte offsets should fall back to display_status."""
    data = {
        "gcode_start_byte": None,
        "gcode_end_byte": None,
        "status": {
            "print_stats": {"filename": "test.gcode"},
            "display_status": {"progress": 0.7},
            "virtual_sdcard": {"file_position": None},
        },
    }

    assert calculate_print_progress(data) == pytest.approx(0.7)


async def test_calculate_print_progress_display_invalid_uses_virtual():
    """Invalid display_status progress should fall back to virtual_sdcard."""
    data = {
        "status": {
            "display_status": {"progress": "bad"},
            "virtual_sdcard": {"progress": 0.45},
        }
    }

    assert calculate_print_progress(data) == pytest.approx(0.45)


async def test_calculate_print_progress_fallback_virtual_sdcard():
    """Fallback to virtual_sdcard when display_status is missing."""
    data = {"status": {"virtual_sdcard": {"progress": 0.4}}}

    assert calculate_print_progress(data) == pytest.approx(0.4)


async def test_calculate_print_progress_invalid_status():
    """Invalid status containers should return 0 progress."""
    assert calculate_print_progress({}) == 0.0
    assert calculate_print_progress({"status": None}) == 0.0
    assert calculate_print_progress(None) == 0.0


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
    get_data["status"]["heater_fan controller_fan"] = {"speed": 0.1234, "rpm": 3000}

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

    state = hass.states.get("sensor.mainsail_fan_rpm")
    assert state is None


async def test_no_fan_rpm(hass, get_data, get_printer_objects_list):
    """Test."""
    get_data["status"]["fan"]["rpm"] = None

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mainsail_fan_rpm") is None

    # Already None in the data
    assert hass.states.get("sensor.mainsail_heater_fan_rpm") is None


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


async def test_total_layer_parses_string_info():
    """Use total layer reported as a string."""
    data = {"status": {"print_stats": {"info": {"total_layer": "12"}}}}

    assert calculate_total_layer(data) == 12


async def test_total_layer_uses_layer_count_string():
    """Fallback to parsed layer count when info is empty."""
    data = {
        "status": {"print_stats": {"info": {"total_layer": 0}}},
        "layer_count": "33.0",
    }

    assert calculate_total_layer(data) == 33


async def test_total_layer_calculated_from_object_height():
    """Calculate total layers using height metadata."""
    data = {
        "status": {"print_stats": {"info": {"total_layer": 0}}},
        "layer_count": 0,
        "object_height": 8.4,
        "layer_height": 0.2,
        "first_layer_height": None,
    }

    assert calculate_total_layer(data) == 42


async def test_total_layer_invalid_metadata_returns_zero():
    """Return zero when height metadata is not usable."""
    data = {
        "status": {"print_stats": {"info": {"total_layer": 0}}},
        "layer_count": 0,
        "object_height": "bad",
        "layer_height": "bad",
    }

    assert calculate_total_layer(data) == 0


async def test_missing_estimated_time(hass, get_data, get_printer_info):
    """Test."""
    del get_data["estimated_time"]

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_data, **get_printer_info},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.mainsail_slicer_print_time_left_estimate")
    assert state.state == "0"

    state2 = hass.states.get("sensor.mainsail_slicer_print_duration_estimate")
    assert state2.state == "0"


async def test_current_layer_calculated():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_calculated_layer_height_str():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": "0.2",
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_calculated_layer_height_0():
    """Test."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
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
                "print_duration": 120,
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
                "print_duration": 120,
                "info": {},
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_uses_virtual_sdcard_filename():
    """Use virtual_sdcard file path when print_stats filename is empty."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "",
                "print_duration": 120,
                "info": {},
            },
            "virtual_sdcard": {"file_path": "TheUniverse.gcode"},
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_zero_info_fallback():
    """Ensure we fall back when current layer info is stuck at zero."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
                "info": {"current_layer": 0, "total_layer": 0},
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_defaults_first_layer_height():
    """Default first layer height to layer height when missing."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
                "info": {},
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 42


async def test_current_layer_non_numeric_position():
    """Return 0 when Z height cannot be interpreted."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
                "info": {},
            },
            "toolhead": {"position": [0, 0, "bad-data"]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 0


async def test_current_layer_negative_progress_clamped():
    """Clamp calculated layer at zero when Z is below first layer."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
                "info": {},
            },
            "toolhead": {"position": [0, 0, 0.1]},
        },
        "first_layer_height": 0.4,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 0


async def test_current_layer_returns_zero_from_info_when_no_fallback():
    """Surface the reported layer when fallback cannot compute."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 120,
                "info": {"current_layer": 0},
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "layer_height": 0,
    }
    assert calculate_current_layer(data) == 0


async def test_current_layer_preheating():
    """Ensure we report 0 while the job is still in preparation."""
    data = {
        "status": {
            "print_stats": {
                "state": PRINTSTATES.PRINTING.value,
                "filename": "TheUniverse.gcode",
                "print_duration": 0,
                "info": {},
            },
            "toolhead": {"position": [0, 0, 8.4]},
        },
        "first_layer_height": 0.2,
        "layer_height": 0.2,
    }
    assert calculate_current_layer(data) == 0


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


async def test_optional_sensor_is_none(hass, get_default_api_response):
    """Test."""
    get_default_api_response["status"]["temperature_sensor mcu_temp"][
        "temperature"
    ] = None
    del get_default_api_response["queued_jobs"]

    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value={**get_default_api_response},
    ):
        config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("sensor.mainsail_mcu_temp")
    assert entity is not None

    state = hass.states.get("sensor.mainsail_mcu_temp")
    assert state.state == "unknown"

    entity = entity_registry.async_get("sensor.mainsail_queue_state")
    assert entity is None

    entity = entity_registry.async_get("sensor.mainsail_jobs_in_queue")
    assert entity is None
