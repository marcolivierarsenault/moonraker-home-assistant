"""Test moonraker config flow."""
from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow

from custom_components.moonraker.const import CONF_PORT, CONF_URL, DOMAIN

from .const import MOCK_CONFIG


async def test_successful_config_flow(hass):
    """Test a successful config flow."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    # If a user were to enter `test_username` for username and `test_password`
    # for password, it would result in this function call
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == MOCK_CONFIG
    assert result["result"]


async def test_tmp_failing_config_flow(hass):
    """Test a failed config flow due to credential validation failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.moonraker.config_flow.MoonrakerFlowHandler._test_connection",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {CONF_URL: "error"}


async def test_server_port_too_low(hass):
    """Test server port when it's too low."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "32"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


async def test_server_port_too_high(hass):
    """Test server port when it's too high."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "4840138103"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


async def test_server_port_not_an_int(hass):
    """Test port when it's not an int."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "1234wdw"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


async def test_server_port_when_good_port(hass):
    """Test server port when it's good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: "7611"}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == {CONF_URL: "1.2.3.4", CONF_PORT: "7611"}
    assert result["result"]


async def test_server_port_when_port_empty(hass):
    """Test server port is left empty"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: ""}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == {CONF_URL: "1.2.3.4", CONF_PORT: ""}
    assert result["result"]
