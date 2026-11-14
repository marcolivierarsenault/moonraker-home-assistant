"""Test moonraker config flow."""

from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant.common import MockConfigEntry

from custom_components.moonraker.const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_STREAM,
    CONF_OPTION_POLLING_RATE,
    DOMAIN,
)

from .const import MOCK_CONFIG, MOCK_OPTIONS


@pytest.fixture(name="bypass_connect_client")
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        yield


@pytest.fixture(name="error_connect_client")
def error_connect_client_fixture():
    """Throw error when trying to connect."""
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        side_effect=Exception,
    ):
        yield


@pytest.mark.usefixtures("bypass_connect_client")
async def test_successful_config_flow(hass):
    """Test a successful config flow."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == MOCK_CONFIG
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_tmp_failing_config_flow(hass):
    """Test a failed config flow due to credential validation failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.moonraker.config_flow.MoonrakerFlowHandler._test_connection",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == FlowResultType.FORM
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
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

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "moonraker"
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "",
        CONF_PRINTER_NAME: "example name",
    }
    assert result["result"]


@pytest.mark.usefixtures("error_connect_client")
async def test_bad_connection_config_flow(hass):
    """Test a config flow with a bad connection."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    assert result["errors"] == {CONF_URL: "printer_connection_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_option_config_camera_services(hass):
    """Test a config flow with camera services."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init("test")
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_OPTION_CAMERA_STREAM: MOCK_OPTIONS[CONF_OPTION_CAMERA_STREAM],
            CONF_OPTION_CAMERA_SNAPSHOT: MOCK_OPTIONS[CONF_OPTION_CAMERA_SNAPSHOT],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("bypass_connect_client")
async def test_option_polling_rate_must_be_positive(hass):
    """The options form rejects a polling rate below 1 second."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init("test")
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_OPTION_POLLING_RATE: 0}
        )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_OPTION_POLLING_RATE: 10}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_OPTION_POLLING_RATE] == 10


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_flow(hass):
    """Test changing the host of a loaded entry keeps its entities."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_ids = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(entity_registry, "test")
    }
    assert entity_ids

    result = await config_entry.start_reconfigure_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_config = {
        **MOCK_CONFIG,
        CONF_URL: "printer.local",
        CONF_PORT: "7125",
        CONF_PRINTER_NAME: "voron",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=new_config
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dict(config_entry.data) == new_config
    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(entity_registry, "test")
    } == entity_ids


async def test_reconfigure_flow_entry_not_ready(hass):
    """Test the entry is set up again after fixing an unreachable host."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.moonraker.MoonrakerApiClient.start",
        side_effect=Exception,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is config_entries.ConfigEntryState.SETUP_RETRY

    with patch("custom_components.moonraker.MoonrakerApiClient.start"):
        result = await config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={**MOCK_CONFIG, CONF_URL: "5.6.7.8"}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_URL] == "5.6.7.8"
    assert config_entry.state is config_entries.ConfigEntryState.LOADED


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_flow_invalid_host(hass):
    """Test the reconfigure flow rejects an invalid host."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**MOCK_CONFIG, CONF_URL: "http://1.2.3.4"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {CONF_URL: "host_error"}
    assert dict(config_entry.data) == MOCK_CONFIG


@pytest.mark.usefixtures("error_connect_client")
async def test_reconfigure_flow_bad_connection(hass):
    """Test the reconfigure flow keeps the entry when the new host fails."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={**MOCK_CONFIG, CONF_URL: "5.6.7.8"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_URL: "printer_connection_error"}
    assert dict(config_entry.data) == MOCK_CONFIG


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_flow_integer_port(hass):
    """Test the reconfigure form accepts an entry that stored the port as int."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data={**MOCK_CONFIG, CONF_PORT: 7125}, entry_id="test"
    )
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)

    assert result["type"] == FlowResultType.FORM
    port_key = next(key for key in result["data_schema"].schema if key == CONF_PORT)
    assert port_key.description == {"suggested_value": "7125"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_flow_clears_optional_fields(hass):
    """Test fields left empty in the reconfigure form are cleared."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_CONFIG, CONF_API_KEY: "a" * 32, CONF_PRINTER_NAME: "voron"},
        entry_id="test",
    )
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    # The frontend omits empty text fields from the submitted data.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "1.2.3.4", CONF_PORT: "1234", CONF_TLS: False},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert config_entry.data[CONF_API_KEY] == ""
    assert config_entry.data[CONF_PRINTER_NAME] == ""


@pytest.mark.parametrize("start_error", [None, Exception])
async def test_connection_probe_is_stopped(hass, start_error):
    """Test the connection probe disconnects whether or not it succeeded."""
    with (
        patch(
            "custom_components.moonraker.MoonrakerApiClient.start",
            side_effect=start_error,
        ),
        patch("custom_components.moonraker.MoonrakerApiClient.stop") as mock_stop,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    mock_stop.assert_awaited_once()


async def test_connection_probe_stop_error_is_ignored(hass):
    """Test a failing disconnect does not change the probe result."""
    with (
        patch("custom_components.moonraker.MoonrakerApiClient.start"),
        patch(
            "custom_components.moonraker.MoonrakerApiClient.stop",
            side_effect=Exception,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY


LOGIN_URL = "http://1.2.3.4:7125/access/login"
API_KEY_URL = "http://1.2.3.4:7125/access/api_key"
LOGOUT_URL = "http://1.2.3.4:7125/access/logout"


@pytest.mark.usefixtures("bypass_connect_client")
async def test_login_fetches_api_key(hass, aioclient_mock):
    """Test username and password are exchanged for the API key."""
    aioclient_mock.post(LOGIN_URL, json={"result": {"token": "jwt"}})
    aioclient_mock.get(API_KEY_URL, json={"result": "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre"})
    aioclient_mock.post(LOGOUT_URL, json={"result": {}})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_URL: "1.2.3.4",
        CONF_PORT: "7125",
        CONF_TLS: False,
        CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
        CONF_PRINTER_NAME: "",
    }
    login_call, key_call, logout_call = aioclient_mock.mock_calls
    assert login_call[2]["username"] == "admin"
    assert login_call[2]["password"] == "secret"
    assert key_call[3] == {"Authorization": "Bearer jwt"}
    assert logout_call[1].path == "/access/logout"


@pytest.mark.usefixtures("bypass_connect_client")
async def test_login_failure(hass, aioclient_mock):
    """Test a failed login shows an error."""
    aioclient_mock.post(LOGIN_URL, status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "wrong",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_USERNAME: "auth_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_api_key_skips_login(hass, aioclient_mock):
    """Test an entered API key is used without logging in."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre"
    assert CONF_USERNAME not in result["data"]
    assert CONF_PASSWORD not in result["data"]
    assert aioclient_mock.call_count == 0


@pytest.mark.usefixtures("bypass_connect_client")
async def test_login_with_tls_verifies_certificate(hass, aioclient_mock):
    """Test the login uses HTTPS with certificate verification when TLS is set."""
    aioclient_mock.post(
        "https://1.2.3.4:7125/access/login", json={"result": {"token": "jwt"}}
    )
    aioclient_mock.get(
        "https://1.2.3.4:7125/access/api_key",
        json={"result": "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre"},
    )
    aioclient_mock.post("https://1.2.3.4:7125/access/logout", json={"result": {}})

    with patch(
        "custom_components.moonraker.config_flow.async_get_clientsession",
        wraps=async_get_clientsession,
    ) as get_session:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_URL: "1.2.3.4",
                CONF_TLS: True,
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre"
    assert all(call[1].scheme == "https" for call in aioclient_mock.mock_calls)
    assert get_session.call_args_list[0].kwargs == {}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_login_fetches_api_key(hass, aioclient_mock):
    """Test reconfigure swaps credentials for the API key without storing them."""
    aioclient_mock.post(LOGIN_URL, json={"result": {"token": "jwt"}})
    aioclient_mock.get(API_KEY_URL, json={"result": "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre"})
    aioclient_mock.post(LOGOUT_URL, json={"result": {}})

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            **MOCK_CONFIG,
            CONF_PORT: "7125",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_API_KEY] == "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre"
    assert CONF_USERNAME not in config_entry.data
    assert CONF_PASSWORD not in config_entry.data


@pytest.mark.usefixtures("bypass_connect_client")
async def test_reconfigure_login_failure(hass, aioclient_mock):
    """Test a failed login during reconfigure shows an error."""
    aioclient_mock.post(LOGIN_URL, status=401)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            **MOCK_CONFIG,
            CONF_PORT: "7125",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "wrong",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_USERNAME: "auth_error"}
    assert CONF_USERNAME not in config_entry.data
