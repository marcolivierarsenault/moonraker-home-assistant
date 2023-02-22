"""Global fixtures for integration_blueprint integration."""
# Fixtures allow you to replace functions with a Mock object. You can perform
# many options via the Mock to reflect a particular behavior from the original
# function that you want to see without going through the function's actual logic.
# Fixtures can either be passed into tests as parameters, or if autouse=True, they
# will automatically be used across all tests.
#
# Fixtures that are defined in conftest.py are available across all tests. You can also
# define fixtures within a particular test file to scope them locally.
#
# pytest_homeassistant_custom_component provides some fixtures that are provided by
# Home Assistant core. You can find those fixture definitions here:
# https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/blob/master/pytest_homeassistant_custom_component/common.py
#
# See here for more info: https://docs.pytest.org/en/latest/fixture.html (note that
# pytest includes fixtures OOB which you can use as defined on this page)
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
                "state": "standby",
                "message": "",
                "filename": "",
                "print_duration": 0.0,
                "filament_used": 0.0,
            },
            "extruder": {"temperature": 33.99, "target": 0.0, "power": 0.0},
            "heater_bed": {"target": 0.0, "temperature": 46.22, "power": 0.0},
            "display_status": {"progress": 0.0},
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
        "estimated_time": 8897.0,
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
        "state": "shutdown",
        "state_message": "Off",
        "hostname": "mainsail",
        "klipper_path": "/home/pi/klipper",
        "python_path": "/home/pi/klippy-env/bin/python",
        "log_file": "/home/pi/printer_data/logs/klippy.log",
        "config_file": "/home/pi/printer_data/config/printer.cfg",
        "software_version": "v0.11.0-89-gead81fbf",
        "cpu_info": "4 core ARMv7 Processor rev 3 (v7l)",
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
