"""Test moonraker config flow."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow

from custom_components.moonraker.const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    DOMAIN,
)

from .const import MOCK_CONFIG


@pytest.fixture(name="bypass_connect_client")
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


@pytest.fixture(name="error_connect_client")
def error_connect_client_fixture():
    """Throw error when trying to connect."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        raise Exception


@pytest.mark.usefixtures("bypass_connect_client")
async def test_successful_config_flow(hass):
    """Test a successful config flow."""
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

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == MOCK_CONFIG
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
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
    assert result["errors"] == {CONF_URL: "printer_connection_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_protocol(hass):
    """Test server host when it has protocol."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "http://1.2.3.4"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_trailing_slash(hass):
    """Test server host when has trailing slash."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "website.com/"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_incomplete_ip(hass):
    """Test server host when has incomplete ip."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_when_good(hass):
    """Test server host when good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4"}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_ssl_enabled(hass):
    """Test server host with TLS."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_TLS: True}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_API_KEY: "",
        CONF_TLS: True,
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_too_low(hass):
    """Test server port when it's too low."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "-32"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_too_high(hass):
    """Test server port when it's too high."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "4840138103"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_not_an_int(hass):
    """Test port when it's not an int."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PORT: "1234wdw"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
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
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7611",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_when_port_empty(hass):
    """Test server port is left empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: ""}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_weird_char(hass):
    """Test api key when contains weird characters."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_API_KEY: "$7ylD3EuPWWxGlsshlCIJjzR$NbQzlre"}
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_too_short(hass):
    """Test api key when it's too short."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_API_KEY: "D7ylD3EuPWWxGlsshlCIJjzRQzlre"}
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_too_long(hass):
    """Test api key when it's too long."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_API_KEY: "D7ylD3EuPWWxGlsshlsd1CIJjzRSNbQzlre"},
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_when_good(hass):
    """Test api key when it's good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
        },
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "moonraker"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_when_empty(hass):
    """Test api key when it's empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
        },
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "moonraker"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "",
    }
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_printer_name_when_invalid(hass):
    """Test printer name when it's invalid."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PRINTER_NAME: "!"}
    )

    assert result["errors"] == {CONF_PRINTER_NAME: "printer_name_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_printer_name_when_good(hass):
    """Test printer name when good."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "1.2.3.4", CONF_PRINTER_NAME: "example name"},
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "moonraker"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "example name",
    }
    assert result["result"]


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
