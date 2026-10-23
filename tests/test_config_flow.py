"""Test moonraker config flow."""

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advance_moonraker_control.const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_STREAM,
    DOMAIN,
)

from .const import MOCK_CONFIG, MOCK_OPTIONS


async def _start_connection_flow(hass):
    """Accept the disclosure before testing connection form validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "requirements"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"accept_requirements": True}
    )


async def _finish_setup(hass, result):
    """Finish with optional features disabled/defaulted."""
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "features"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_requirements_must_be_accepted_before_connecting(hass):
    """Opening, declining and cancelling must not contact a printer."""
    with patch("custom_components.advance_moonraker_control.config_flow.MoonrakerApiClient") as client:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "requirements"
        assert result["data_schema"]({}) == {"accept_requirements": False}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"accept_requirements": False}
        )
        assert result["errors"] == {"base": "requirements_not_accepted"}
        assert not hass.config_entries.async_entries(DOMAIN)
        client.assert_not_called()
        hass.config_entries.flow.async_abort(result["flow_id"])
        client.assert_not_called()


async def test_installation_requires_consent_even_with_supplied_data(hass):
    """Flow initialization cannot bypass consent by supplying connection data."""
    with patch("custom_components.advance_moonraker_control.config_flow.MoonrakerApiClient") as client:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=MOCK_CONFIG
        )
        assert result["step_id"] == "requirements"
        client.assert_not_called()


async def test_features_cannot_skip_connection(hass):
    """A direct feature-step call cannot create an unvalidated entry."""
    from custom_components.advance_moonraker_control.config_flow import MoonrakerFlowHandler

    flow = MoonrakerFlowHandler()
    flow.hass = hass
    result = await flow.async_step_features({})
    assert result["step_id"] == "requirements"
    await flow.async_step_requirements({"accept_requirements": True})
    result = await flow.async_step_features({})
    assert result["step_id"] == "user"
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_installation_saves_features_and_only_reads_printer_info(hass):
    """The wizard keeps credentials separate from options and closes its client."""
    result = await _start_connection_flow(hass)
    with (
        patch("custom_components.advance_moonraker_control.config_flow.MoonrakerApiClient") as client,
        patch("custom_components.advance_moonraker_control.async_setup_entry", return_value=True),
    ):
        api = client.return_value
        api.start = AsyncMock()
        api.stop = AsyncMock()
        api.client.call_method = AsyncMock(return_value={"state": "ready"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], MOCK_CONFIG
        )
        assert result["step_id"] == "features"
        assert not hass.config_entries.async_entries(DOMAIN)
        api.client.call_method.assert_awaited_once_with("printer.info")
        api.stop.assert_awaited_once()
        options = {CONF_OPTION_POLLING_RATE: 30}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], options
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == MOCK_CONFIG
        assert result["options"][CONF_OPTION_POLLING_RATE] == 30
        assert CONF_API_KEY not in result["options"]
        assert "accept_requirements" not in result["data"]
        assert "power_switch_entity" not in result["options"]
        await hass.async_block_till_done()


@pytest.mark.usefixtures("bypass_connect_client")
@pytest.mark.parametrize(
    ("options", "errors"),
    [
        ({"power_sensor": "sensor.missing"}, {"power_sensor": "entity_missing"}),
        ({"notify_service": "missing"}, {"notify_service": "notify_missing"}),
        ({"camera_port": "not-a-port"}, {"camera_port": "port_error"}),
        ({"thumbnail_port": "65536"}, {"thumbnail_port": "port_error"}),
        (
            {"ai_task_entity": "ai_task.vision"},
            {"base": "vision_requires_pair"},
        ),
        (
            {"vision_camera": "camera.printer"},
            {"base": "vision_requires_pair"},
        ),
    ],
)
async def test_missing_optional_requirements_can_be_corrected(hass, options, errors):
    """Unavailable optional services block only completion, not correction."""
    hass.states.async_set("ai_task.vision", "idle")
    hass.states.async_set("camera.printer", "idle")
    result = await _start_connection_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_CONFIG
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], options)
    assert result["step_id"] == "features"
    assert result["errors"] == errors
    assert not hass.config_entries.async_entries(DOMAIN)
    # An empty selection disables the optional dependency; start with a fresh
    # schema's defaults, because the correction form retains submitted values.
    from custom_components.advance_moonraker_control.config_flow import OptionsFlowHandler

    defaults = OptionsFlowHandler.options_schema({})({})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], defaults)
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("bypass_connect_client")
async def test_available_optional_services_are_saved_without_being_called(hass):
    """Configuring dependencies must not activate them or send camera images."""
    hass.states.async_set("ai_task.vision", "idle")
    hass.states.async_set("camera.printer", "idle")
    hass.states.async_set("switch.printer", "on")
    handler = AsyncMock()
    hass.services.async_register("notify", "printer", handler)
    result = await _start_connection_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_CONFIG
    )
    with patch("custom_components.advance_moonraker_control.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "ai_task_entity": "ai_task.vision",
                "vision_camera": "camera.printer",
                "power_switch_entity": "switch.printer",
                "notify_service": "printer",
                "camera_port": "8080",
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["options"]["camera_port"] == "8080"
        assert result["options"]["power_switch_entity"] == "switch.printer"
        handler.assert_not_called()
        assert hass.states.get("switch.printer").state == "on"
        await hass.async_block_till_done()


async def test_options_reject_missing_service_and_allow_correction(hass):
    """Later configuration checks requirements just like initial installation."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_service": "missing"}
    )
    assert result["errors"] == {"notify_service": "notify_missing"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_service": ""}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["notify_service"] == ""


@pytest.fixture(name="bypass_connect_client")
def bypass_connect_client_fixture():
    """Skip calls to get data from API."""
    with (
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.start"),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
    ):
        yield


@pytest.fixture(name="error_connect_client")
def error_connect_client_fixture():
    """Throw error when trying to connect."""
    with (
        patch(
            "custom_components.advance_moonraker_control.MoonrakerApiClient.start",
            side_effect=Exception,
        ),
        patch("custom_components.advance_moonraker_control.MoonrakerApiClient.stop"),
    ):
        yield


@pytest.mark.usefixtures("bypass_connect_client")
async def test_successful_config_flow(hass):
    """Test a successful config flow."""
    # Initialize a config flow
    result = await _start_connection_flow(hass)

    # Check that the config flow shows the user form as the first step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.advance_moonraker_control.MoonrakerApiClient.stop",
        new_callable=AsyncMock,
    ) as stop_client:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    stop_client.assert_awaited_once()
    result = await _finish_setup(hass, result)

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == DOMAIN
    assert result["data"] == MOCK_CONFIG
    assert result["result"]


@pytest.mark.usefixtures("bypass_connect_client")
async def test_tmp_failing_config_flow(hass):
    """Test a failed config flow due to credential validation failure."""
    result = await _start_connection_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.advance_moonraker_control.config_flow.MoonrakerFlowHandler._test_connection",
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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "http://1.2.3.4"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_trailing_slash(hass):
    """Test server host when has trailing slash."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "website.com/"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_with_incomplete_ip(hass):
    """Test server host when has incomplete ip."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3"}
    )

    assert result["errors"] == {CONF_URL: "host_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_host_when_good(hass):
    """Test server host when good."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4"}
    )
    result = await _finish_setup(hass, result)

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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_TLS: True}
    )
    result = await _finish_setup(hass, result)

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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: "-32"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_too_high(hass):
    """Test server port when it's too high."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: "4840138103"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_not_an_int(hass):
    """Test port when it's not an int."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: "1234wdw"}
    )
    assert result["errors"] == {CONF_PORT: "port_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_port_when_good_port(hass):
    """Test server port when it's good."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: "7611"}
    )
    result = await _finish_setup(hass, result)

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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PORT: ""}
    )
    result = await _finish_setup(hass, result)

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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_API_KEY: "$7ylD3EuPWWxGlsshlCIJjzR$NbQzlre",
        },
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_too_short(hass):
    """Test api key when it's too short."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "1.2.3.4", CONF_API_KEY: "D7ylD3EuPWWxGlsshlCIJjzRQzlre"},
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_too_long(hass):
    """Test api key when it's too long."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_API_KEY: "D7ylD3EuPWWxGlsshlsd1CIJjzRSNbQzlre",
        },
    )
    assert result["errors"] == {CONF_API_KEY: "api_key_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_server_api_key_when_good(hass):
    """Test api key when it's good."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
            CONF_API_KEY: "A7ylD3EuPWWxGlsshlCIJjzRBNbQzlre",
        },
    )

    result = await _finish_setup(hass, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "advance_moonraker_control"
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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_URL: "1.2.3.4",
        },
    )

    result = await _finish_setup(hass, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "advance_moonraker_control"
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
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_URL: "1.2.3.4", CONF_PRINTER_NAME: "!"}
    )

    assert result["errors"] == {CONF_PRINTER_NAME: "printer_name_error"}


@pytest.mark.usefixtures("bypass_connect_client")
async def test_printer_name_when_good(hass):
    """Test printer name when good."""
    result = await _start_connection_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "1.2.3.4", CONF_PRINTER_NAME: "example name"},
    )

    result = await _finish_setup(hass, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "advance_moonraker_control"
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
    result = await _start_connection_flow(hass)

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
async def test_polling_rate_options_enforce_minimum(hass):
    """Polling-rate options should reject values below the safe minimum."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options={CONF_OPTION_POLLING_RATE: 2},
        entry_id="polling_options",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"]

    assert schema({})[CONF_OPTION_POLLING_RATE] == 7
    assert schema({CONF_OPTION_POLLING_RATE: 7})[CONF_OPTION_POLLING_RATE] == 7
    with pytest.raises(vol.Invalid):
        schema({CONF_OPTION_POLLING_RATE: 6})
