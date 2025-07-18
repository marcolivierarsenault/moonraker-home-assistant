"""Global fixtures for integration_blueprint integration."""

from unittest.mock import patch

import pytest

PYTEST_PLUGINS = "pytest_homeassistant_custom_component"


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto enable custom integrations."""
    del enable_custom_integrations
    yield


@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    """Temporary ability to bypass test failures.

    Parametrize to True to bypass the pytest failure.
    @pytest.mark.parametrize("expected_lingering_timers", [True])
    This should be removed when all lingering timers have been cleaned up.
    """
    return True


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


@pytest.fixture(name="get_data")
def get_data_fixture():
    """Get data Fixture."""
    return {
        "eventtime": 128684.342831779,
        "status": {
            "system_stats": {
                "sysload": 0.244140625,
                "cputime": 384.86964173,
                "memavail": 1291812,
            },
            "configfile": {
                "settings": {
                    "output_pin digital": {
                        "pwm": False,
                    },
                    "output_pin pwm": {
                        "pwm": True,
                    },
                    "output_pin capitalized": {
                        "pwm": True,
                    },
                    "led chamber": {
                        "white_pin": "PA1",
                        "red_pin": "PA2",
                        "blue_pin": "PA3",
                        "green_pin": "PA4",
                    },
                    "neopixel camera": {
                        "pin": "PA5",
                        "color_order": "RGBW",
                    },
                    "dotstar strip": {
                        "pin": "PA6",
                    },
                    "pca9533 leds": {
                        "pin": "PA7",
                    },
                    "led ignored_no_pins": {},
                    "led brightness_only": {
                        "white_pin": "PA8",
                    },
                    "neopixel rgb_only": {
                        "pin": "PA9",
                    },
                    "led generic_rgb": {
                        "red_pin": "PA10",
                        "blue_pin": "PA11",
                        "green_pin": "PA12",
                    },
                },
            },
            "print_stats": {
                "filename": "CE3E3V2_picture_frame_holder.gcode",
                "total_duration": 8232.396654963959,
                "print_duration": 8014.528148686048,
                "filament_used": 5000.00,
                "state": "printing",
                "message": "",
                "info": {"total_layer": 33, "current_layer": 22},
            },
            "toolhead": {
                "homed_axes": "xyz",
                "print_time": 0.0,
                "estimated_print_time": 0.0,
                "extruder": "extruder",
                "position": [23.30234, 22.20234, 10.20234, 234.2],
                "max_velocity": 500.0,
                "max_accel": 3000.0,
                "max_accel_to_decel": 1500.0,
                "square_corner_velocity": 5.0,
            },
            "extruder": {
                "temperature": 205.02,
                "target": 205.0,
                "power": 0.6667108063925052,
                "can_extrude": True,
                "pressure_advance": 0.325,
                "smooth_time": 0.04,
            },
            "extruder1": {
                "temperature": 220.01,
                "target": 220.0,
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
            "heater_generic my_super_heater": {
                "temperature": 32.43,
                "target": 32.0,
                "power": 0.1234,
            },
            "temperature_sensor mcu_temp": {
                "temperature": 32.43,
            },
            "temperature_fan fan_temp": {
                "temperature": 32.43,
            },
            "fan_generic nevermore_fan": {
                "speed": 0.1234,
                "rpm": 4500.23231,
            },
            "temperature_probe eddy_temp": {
                "temperature": 32.43,
            },
            "temperature_host host_temp": {
                "temperature": 32.43,
            },
            "bme280 bme280_temp": {
                "temperature": 32.43,
                "pressure": 988.1478719193026,
                "humidity": 26.783619296566297,
                "gas": 36351.74625591767,
            },
            "tmc2240 tmc2240_stepper_x_temp": {
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
                "rpm": 3000.12321,
            },
            "heater_fan heater_fan": {
                "speed": 0.5123,
                "rpm": None,
            },
            "controller_fan controller_fan": {
                "speed": 0.5123,
                "rpm": 5000.32123,
            },
            "filament_switch_sensor filament_sensor_1": {
                "filament_detected": True,
                "enabled": True,
            },
            "filament_switch_sensor filament_sensor_2": {
                "filament_detected": True,
                "enabled": True,
            },
            "output_pin digital": {
                "value": 1.0,
            },
            "output_pin pwm": {
                "value": 0.5,
            },
            "output_pin CAPITALIZED": {
                "value": 1.0,
            },
            "led chamber": {
                "color_data": [[0.0, 0.0, 0.0, 0.5]],
            },
            "neopixel CAMERA": {
                "color_data": [[1.0, 0.5, 0.0, 0.0]],
            },
            "dotstar strip": {
                "color_data": [[1.0, 0.5, 0.0, 0.0]],
            },
            "pca9533 leds": {
                "color_data": [[1.0, 0.5, 0.0, 0.0]],
            },
            "led ignored_no_pins": {
                "color_data": [[1.0, 0.5, 0.0, 0.0]],
            },
            "led brightness_only": {
                "color_data": [[1.0, 0.5, 0.0, 0.0]],
            },
            "neopixel rgb_only": {
                "color_data": [[1.0, 0.5, 0.0, 0.0]],
            },
            "led generic_rgb": {
                "color_data": [[1.0, 0.5, 1.0, 0.0]],
            },
            "gcode_move": {
                "speed_factor": 2.0,
            },
            "mcu": {
                "last_stats": {
                    "mcu_awake": 0.031,
                    "mcu_task_avg": 0.000002,
                    "mcu_task_stddev": 0.000012,
                },
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
        "history": {
            "job_totals": {
                "total_jobs": 3,
                "total_time": 11748.077333278954,
                "total_print_time": 11348.794790096988,
                "total_filament_used": 11615.718840001999,
                "longest_job": 11665.191012736992,
                "longest_print": 11348.794790096988,
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
        "queued_jobs": [],
        "queue_state": "paused",
    }


@pytest.fixture(name="get_printer_info")
def get_printer_info_fixture():
    """Get printer info fixture."""
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
    """Get gcode help fixture."""
    return {
        "SET_PAUSE_NEXT_LAYER": "Enable a pause if the next layer is reached",
        "SET_PAUSE_AT_LAYER": "Enable/disable a pause if a given layer number is reached",
        "_TOOLHEAD_PARK_PAUSE_CANCEL": "Helper: park toolhead used in PAUSE and CANCEL_PRINT",
        "_CLIENT_EXTRUDE": "Extrudes, if the extruder is hot enough",
        "_CLIENT_RETRACT": "Retracts, if the extruder is hot enough",
        "START_PRINT": "G-Code macro",
        "END_PRINT": "G-Code macro",
    }


@pytest.fixture(name="get_system_info")
def get_system_info_fixture():
    """Get system info fixture."""
    return {
        "system_info": {
            "provider": "systemd_dbus",
            "cpu_info": {
                "cpu_count": 4,
                "bits": "32bit",
                "processor": "armv7l",
                "cpu_desc": "ARMv7 Processor rev 4 (v7l)",
                "serial_number": "b898bdb4",
                "hardware_desc": "BCM2835",
                "model": "Raspberry Pi 3 Model B Rev 1.2",
                "total_memory": 945364,
                "memory_units": "kB",
            },
            "sd_info": {
                "manufacturer_id": "03",
                "manufacturer": "Sandisk",
                "oem_id": "5344",
                "product_name": "SU32G",
                "product_revision": "8.0",
                "serial_number": "46ba46",
                "manufacturer_date": "4/2018",
                "capacity": "29.7 GiB",
                "total_bytes": 31914983424,
            },
            "distribution": {
                "name": "Raspbian GNU/Linux 10 (buster)",
                "id": "raspbian",
                "version": "10",
                "version_parts": {"major": "10", "minor": "", "build_number": ""},
                "like": "debian",
                "codename": "buster",
            },
            "available_services": ["klipper", "klipper_mcu", "moonraker"],
            "instance_ids": {"moonraker": "moonraker", "klipper": "klipper"},
            "service_state": {
                "klipper": {"active_state": "active", "sub_state": "running"},
                "klipper_mcu": {"active_state": "active", "sub_state": "running"},
                "moonraker": {"active_state": "active", "sub_state": "running"},
            },
            "virtualization": {"virt_type": "none", "virt_identifier": "none"},
            "python": {
                "version": [3, 9, 2, "final", 0],
                "version_string": "3.9.2 (default, Feb 28 2021, 17:03:44)  [GCC 10.2.1 20210110]",
            },
            "network": {
                "wlan0": {
                    "mac_address": "<redacted_mac>",
                    "ip_addresses": [
                        {
                            "family": "ipv4",
                            "address": "192.168.1.127",
                            "is_link_local": "false",
                        },
                        {
                            "family": "ipv6",
                            "address": "<redacted_ipv6>",
                            "is_link_local": "false",
                        },
                        {
                            "family": "ipv6",
                            "address": "fe80::<redacted>",
                            "is_link_local": "true",
                        },
                    ],
                }
            },
            "canbus": {
                "can0": {"tx_queue_len": 128, "bitrate": 500000, "driver": "mcp251x"},
                "can1": {"tx_queue_len": 128, "bitrate": 500000, "driver": "gs_usb"},
            },
        }
    }


@pytest.fixture(name="get_printer_objects_list")
def get_printer_objects_list_fixture():
    """Get printer objects list fixture."""
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
            "heater_generic my_super_heater",
            "fan",
            "probe",
            "bed_mesh",
            "screws_tilt_adjust",
            "temperature_sensor mcu_temp",
            "temperature_probe eddy_temp",
            "stepper_enable",
            "motion_report",
            "query_endstops",
            "system_stats",
            "manual_probe",
            "toolhead",
            "extruder",
            "extruder1",
            "temperature_fan fan_temp",
            "temperature_host host_temp",
            "bme280 bme280_temp",
            "tmc2240 tmc2240_stepper_x_temp",
            "htu21d htu21d_temp",
            "lm75 lm75_temp",
            "heater_fan heater_fan",
            "controller_fan controller_fan",
            "filament_switch_sensor filament_sensor_1",
            "filament_switch_sensor filament_sensor_2",
            "output_pin digital",
            "output_pin pwm",
            "output_pin CAPITALIZED",
            "led chamber",
            "neopixel CAMERA",
            "dotstar strip",
            "pca9533 leds",
            "led ignored_no_pins",
            "led brightness_only",
            "neopixel rgb_only",
            "led generic_rgb",
            "fan_generic nevermore_fan",
        ]
    }


@pytest.fixture(name="get_camera_info")
def get_camera_info_fixture():
    """Get camera info fixture."""
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


@pytest.fixture(name="get_history")
def get_history_fixture():
    """Get history fixture."""
    return {
        "job_totals": {
            "total_jobs": 3,
            "total_time": 11748.077333278954,
            "total_print_time": 11348.794790096988,
            "total_filament_used": 11615.718840001999,
            "longest_job": 11665.191012736992,
            "longest_print": 11348.794790096988,
        }
    }


@pytest.fixture(name="get_power_devices")
def get_power_devices_fixture():
    """Get power devices fixture."""
    return {
        "devices": [
            {
                "device": "printer",
                "status": "on",
                "locked_while_printing": False,
                "type": "tplink_smartplug",
            },
            {
                "device": "light",
                "status": "off",
                "locked_while_printing": False,
                "type": "tplink_smartplug",
            },
        ]
    }


@pytest.fixture(name="get_machine_update_status")
def get_machine_update_status_fixture():
    """Get Machine Update Status fixture."""
    return {
        "version_info": {
            "system": {"package_count": 8},
            "crownest": {"version": "v4.0.4-6", "remote_version": "v4.1.1-1"},
            "mainsail": {"version": "v2.8.0", "remote_version": "v2.8.0"},
        },
    }


@pytest.fixture(name="get_machine_system_info")
def get_machine_system_info_fixture():
    """Get Machine Update Status fixture."""
    return {
        "system_info": {
            "cpu_info": {
                "cpu_count": 4,
                "bits": "64bit",
                "processor": "aarch64",
                "cpu_desc": "",
                "serial_number": "10000000e2e0a55f",
                "hardware_desc": "",
                "model": "Raspberry Pi Compute Module 4 Rev 1.1",
                "total_memory": 1891256,
                "memory_units": "kB",
            },
        }
    }


@pytest.fixture(name="get_default_api_response")
def get_default_api_response_fixure(
    get_data,
    get_printer_info,
    get_printer_objects_list,
    get_history,
    get_camera_info,
    get_gcode_help,
    get_power_devices,
    get_machine_update_status,
    get_machine_system_info,
    get_system_info,
):
    """Get all the default fixture returned by moonraker."""
    return {
        **get_data,
        **get_printer_info,
        **get_printer_objects_list,
        **get_history,
        **get_camera_info,
        **get_gcode_help,
        **get_power_devices,
        **get_machine_update_status,
        **get_machine_system_info,
        **get_system_info,
    }


@pytest.fixture(name="_moonraker_default_mock", autouse=True)
def get_moonraker_default_mock(get_default_api_response):
    """Return mock for moonraker API."""
    with patch(
        "moonraker_api.MoonrakerClient.call_method",
        return_value=get_default_api_response,
    ):
        yield
