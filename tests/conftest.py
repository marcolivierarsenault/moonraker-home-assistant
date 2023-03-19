"""Global fixtures for integration_blueprint integration."""
from unittest.mock import patch

import pytest

PYTEST_PLUGINS = "pytest_homeassistant_custom_component"


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto enable custom integrations"""
    del enable_custom_integrations
    yield


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield


@pytest.fixture(name="get_data")
def get_data_fixture():
    """Get data Fixture"""
    return {
        "eventtime": 128684.342831779,
        "status": {
            "print_stats": {
                "filename": "CE3E3V2_picture_frame_holder.gcode",
                "total_duration": 8232.396654963959,
                "print_duration": 8014.528148686048,
                "filament_used": 5000.00,
                "state": "printing",
                "message": "",
                "info": {"total_layer": None, "current_layer": None},
            },
            "extruder": {
                "temperature": 205.02,
                "target": 205.0,
                "power": 0.6667108063925052,
                "can_extrude": True,
                "pressure_advance": 0.325,
                "smooth_time": 0.04,
            },
            "heater_bed": {
                "temperature": 60.01,
                "target": 60.0,
                "power": 0.26053745272533363,
            },
            "temperature_sensor mcu_temp": {
                "temperature": 32.43,
            },
            "temperature_fan fan_temp": {
                "temperature": 32.43,
            },
            "temperature_host host_temp": {
                "temperature": 32.43,
            },
            "bme280 bme280_temp": {
                "temperature": 32.43,
            },
            "htu21d htu21d_temp": {
                "temperature": 32.43,
            },
            "lm75 lm75_temp": {
                "temperature": 32.43,
            },
            "display_status": {
                "progress": 0.9078104237663283,
                "message": "Custom Message",
            },
            "fan": {
                "speed": 0.5123,
                "rpm": 3000,
            },
            "heater_fan heater_fan": {
                "speed": 0.5123,
                "rpm": 3000,
            },
            "controller_fan controller_fan": {
                "speed": 0.5123,
                "rpm": 3000,
            },
        },
        "printer.info": {
            "result": {
                "state": "ready",
                "state_message": "Printer is ready",
                "hostname": "mainsail",
                "klipper_path": "/home/pi/klipper",
                "python_path": "/home/pi/klippy-env/bin/python",
                "log_file": "/home/pi/printer_data/logs/klippy.log",
                "config_file": "/home/pi/printer_data/config/printer.cfg",
                "software_version": "v0.11.0-89-gead81fbf",
                "cpu_info": "4 core ARMv7 Processor rev 3 (v7l)",
            }
        },
        "size": 3433628,
        "modified": 1675395952.8169234,
        "uuid": "76ae56ef-3391-4f7a-89b4-8cc1cb4d6454",
        "slicer": "Cura",
        "slicer_version": "5.2.1",
        "gcode_start_byte": 193,
        "gcode_end_byte": 3432865,
        "layer_count": 313,
        "object_height": 62.6,
        "estimated_time": 8232.0,
        "layer_height": 0.2,
        "first_layer_height": 0.2,
        "filament_total": 5988.32,
        "thumbnails": [
            {
                "width": 32,
                "height": 32,
                "size": 1259,
                "relative_path": ".thumbs/CE3E3V2_picture_frame_holder-32x32.png",
            },
            {
                "width": 300,
                "height": 300,
                "size": 9040,
                "relative_path": ".thumbs/CE3E3V2_picture_frame_holder.png",
            },
        ],
        "print_start_time": 1675396166.8472495,
        "job_id": "000059",
        "filename": "CE3E3V2_picture_frame_holder.gcode",
    }


@pytest.fixture(name="get_printer_info")
def get_printer_info_fixture():
    """Get printer info fixture"""
    return {
        "state": "ready",
        "state_message": "Printer is ready",
        "hostname": "mainsail",
        "klipper_path": "/home/pi/klipper",
        "python_path": "/home/pi/klippy-env/bin/python",
        "log_file": "/home/pi/printer_data/logs/klippy.log",
        "config_file": "/home/pi/printer_data/config/printer.cfg",
        "software_version": "v0.11.0-89-gead81fbf",
        "cpu_info": "4 core ARMv7 Processor rev 3 (v7l)",
    }


@pytest.fixture(name="get_gcode_help")
def get_gcode_help_fixture():
    """Get gcode help fixture"""
    return {
        "SET_PAUSE_NEXT_LAYER": "Enable a pause if the next layer is reached",
        "SET_PAUSE_AT_LAYER": "Enable/disable a pause if a given layer number is reached",
        "_TOOLHEAD_PARK_PAUSE_CANCEL": "Helper: park toolhead used in PAUSE and CANCEL_PRINT",
        "_CLIENT_EXTRUDE": "Extrudes, if the extruder is hot enough",
        "_CLIENT_RETRACT": "Retracts, if the extruder is hot enough",
        "START_PRINT": "G-Code macro",
        "END_PRINT": "G-Code macro",
    }


@pytest.fixture(name="get_printer_objects_list")
def get_printer_objects_list_fixture():
    """Get printer objects list fixture"""
    return {
        "objects": [
            "webhooks",
            "configfile",
            "mcu",
            "gcode_move",
            "print_stats",
            "virtual_sdcard",
            "pause_resume",
            "display_status",
            "gcode_macro CANCEL_PRINT",
            "gcode_macro PAUSE",
            "gcode_macro RESUME",
            "idle_timeout",
            "heaters",
            "heater_bed",
            "fan",
            "probe",
            "bed_mesh",
            "screws_tilt_adjust",
            "temperature_sensor mcu_temp",
            "stepper_enable",
            "motion_report",
            "query_endstops",
            "system_stats",
            "manual_probe",
            "toolhead",
            "extruder",
            "temperature_fan fan_temp",
            "temperature_host host_temp",
            "bme280 bme280_temp",
            "htu21d htu21d_temp",
            "lm75 lm75_temp",
            "heater_fan heater_fan",
            "controller_fan controller_fan",
        ]
    }


@pytest.fixture(name="get_camera_info")
def get_camera_info_fixture():
    """Get camera info fixture"""
    return {
        "webcams": [
            {
                "name": "webcam",
                "location": "printer",
                "service": "mjpegstreamer-adaptive",
                "target_fps": "15",
                "stream_url": "/webcam/?action=stream",
                "snapshot_url": "/webcam/?action=snapshot",
                "flip_horizontal": False,
                "flip_vertical": False,
                "rotation": 0,
                "source": "database",
            }
        ]
    }
