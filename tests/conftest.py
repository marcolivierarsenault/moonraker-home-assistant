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

pytest_plugins = "pytest_homeassistant_custom_component"


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
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


@pytest.fixture(name="bypass_connect_client")
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.connect_client"):
        yield


@pytest.fixture(name="error_on_get_data")
def error_get_data_fixture():
    """Simulate error when retrieving data from API."""
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.get_data",
        side_effect=Exception,
    ):
        yield


@pytest.fixture(name="get_data")
def get_data_fixture():
    return {
        "webhooks": {"state": "ready", "state_message": "Printer is ready"},
        "extruder": {
            "temperature": 21.17,
            "target": 0.0,
            "power": 0.0,
            "can_extrude": False,
            "pressure_advance": 0.65,
            "smooth_time": 0.04,
        },
        "heater_bed": {"temperature": 22.25, "target": 0.0, "power": 0.0},
        "print_stats": {
            "filename": "",
            "total_duration": 0.0,
            "print_duration": 0.0,
            "filament_used": 0.0,
            "state": "standby",
            "message": "",
            "info": {"total_layer": None, "current_layer": None},
        },
        "display_status": {"progress": 0.0, "message": "speed F4800"},
        "filament_switch_sensor": {},
    }
