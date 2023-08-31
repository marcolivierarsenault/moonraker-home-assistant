"""Test moonraker config flow."""
from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
import pytest

from custom_components.moonraker.const import CONF_URL, DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(name="error_connect_client")
def error_connect_client_fixture():
    """Throw error when trying to connect"""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        raise Exception


async def test_bad_connection_config_flow(hass):
    """Test a config flow with a bad connection."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    assert result["errors"] == {CONF_URL: "printer_connection_error"}
