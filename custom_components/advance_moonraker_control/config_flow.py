"""Adds config flow for Moonraker."""

import logging

from typing import Any

import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import network, slugify

from .api import MoonrakerApiClient
from .const import (
    CONF_OPTION_AI_TASK_ENTITY,
    CONF_OPTION_AMBIENT_SENSOR,
    CONF_OPTION_ENERGY_RATE,
    CONF_OPTION_HUMIDITY_SENSOR,
    CONF_OPTION_MAX_FLOW,
    CONF_OPTION_NOTIFY_SERVICE,
    CONF_OPTION_POWER_OFF_DELAY,
    CONF_OPTION_PANEL_ROLE,
    CONF_OPTION_POWER_OFF_MAX_TEMP,
    CONF_OPTION_POWER_SENSOR,
    CONF_OPTION_VISION_CAMERA,
    CONF_OPTION_POWER_SWITCH,
    DEFAULT_MAX_FLOW_MM3,
    DEFAULT_POWER_OFF_DELAY_MIN,
    DEFAULT_POWER_OFF_MAX_TEMP,
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    DEFAULT_PORT,
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_QUIET_UNREACHABLE,
    DEFAULT_POLLING_RATE,
    MIN_POLLING_RATE,
    CONF_OPTION_CAMERA_STREAM,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_PORT,
    CONF_OPTION_THUMBNAIL_PORT,
    DOMAIN,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


def _feature_errors(hass, options):
    """Check selected optional dependencies without installing external services."""
    errors = {}
    for key in (
        CONF_OPTION_POWER_SENSOR,
        CONF_OPTION_POWER_SWITCH,
        CONF_OPTION_AMBIENT_SENSOR,
        CONF_OPTION_HUMIDITY_SENSOR,
        CONF_OPTION_AI_TASK_ENTITY,
        CONF_OPTION_VISION_CAMERA,
    ):
        if options.get(key) and hass.states.get(options[key]) is None:
            errors[key] = "entity_missing"
    if bool(options.get(CONF_OPTION_AI_TASK_ENTITY)) != bool(
        options.get(CONF_OPTION_VISION_CAMERA)
    ):
        errors["base"] = "vision_requires_pair"
    service = options.get(CONF_OPTION_NOTIFY_SERVICE)
    if service and not hass.services.has_service("notify", service):
        errors[CONF_OPTION_NOTIFY_SERVICE] = "notify_missing"
    for key in (CONF_OPTION_CAMERA_PORT, CONF_OPTION_THUMBNAIL_PORT):
        port = options.get(key)
        if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
            errors[key] = "port_error"
    return errors


class MoonrakerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Moonraker."""

    VERSION = 2

    def __init__(self):
        """Initialize."""
        _LOGGER.debug("loading moonraker confFlowHandler")
        self._errors = {}
        self._requirements_accepted = False
        self._connection_data = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if not self._requirements_accepted:
            return await self.async_step_requirements()
        self._errors = {}

        if user_input is not None:
            if not await self._test_host(user_input[CONF_URL]):
                self._errors[CONF_URL] = "host_error"
                return await self._show_config_form(user_input)

            if not await self._test_port(user_input[CONF_PORT]):
                self._errors[CONF_PORT] = "port_error"
                return await self._show_config_form(user_input)

            if not await self._test_api_key(user_input[CONF_API_KEY]):
                self._errors[CONF_API_KEY] = "api_key_error"
                return await self._show_config_form(user_input)

            if not await self._test_printer_name(user_input[CONF_PRINTER_NAME]):
                self._errors[CONF_PRINTER_NAME] = "printer_name_error"
                return await self._show_config_form(user_input)

            if not await self._test_connection(
                user_input[CONF_URL],
                user_input[CONF_PORT],
                user_input[CONF_API_KEY],
                user_input[CONF_TLS],
            ):
                self._errors[CONF_URL] = "printer_connection_error"
                return await self._show_config_form(user_input)

            self._connection_data = user_input
            return await self.async_step_features()

        user_input = {}
        # Provide defaults for form
        user_input[CONF_URL] = ""
        user_input[CONF_PORT] = "7125"
        user_input[CONF_TLS] = False
        user_input[CONF_API_KEY] = ""
        user_input[CONF_PRINTER_NAME] = ""

        return await self._show_config_form(user_input)

    async def async_step_requirements(self, user_input=None):
        """Require consent before opening a connection to a printer."""
        errors = {}
        if user_input is not None:
            if user_input.get("accept_requirements") is True:
                self._requirements_accepted = True
                return await self.async_step_user()
            errors["base"] = "requirements_not_accepted"
        return self.async_show_form(
            step_id="requirements",
            data_schema=vol.Schema(
                {vol.Required("accept_requirements", default=False): bool}
            ),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/thaliamontreux/"
                "HACS_Moonraker_Advanced#installation"
            },
        )

    async def async_step_features(self, user_input=None):
        """Configure optional features before setting up the integration."""
        if not self._requirements_accepted or not self._connection_data:
            return await self.async_step_user()
        errors = _feature_errors(self.hass, user_input or {})
        if user_input is not None and not errors:
            return self.async_create_entry(
                title=DOMAIN, data=self._connection_data, options=user_input
            )
        return self.async_show_form(
            step_id="features",
            data_schema=OptionsFlowHandler.options_schema(user_input or {}),
            errors=errors,
        )

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit location data."""

        _LOGGER.debug("Showing moonraker conf")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=user_input[CONF_URL]): str,
                    vol.Optional(CONF_PORT, default=user_input[CONF_PORT]): str,
                    vol.Optional(CONF_TLS, default=user_input[CONF_TLS]): bool,
                    vol.Optional(
                        CONF_API_KEY, default=user_input[CONF_API_KEY]
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(
                        CONF_PRINTER_NAME, default=user_input[CONF_PRINTER_NAME]
                    ): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_host(self, host: str):
        return network.is_host_valid(host)

    async def _test_port(self, port):
        if port != "":
            if not port.isdigit() or int(port) > 65535 or int(port) <= 1:
                return False
        return True

    async def _test_api_key(self, api_key):
        if api_key != "":
            if not api_key.isalnum() or len(api_key) != 32:
                return False
        return True

    async def _test_printer_name(self, printer_name):
        slugified_name = slugify(printer_name)

        if slugified_name == "unknown":
            return False

        return True

    async def _test_connection(self, host, port, api_key, tls):
        effective_port = DEFAULT_PORT if port == "" else port
        api = MoonrakerApiClient(
            host,
            async_get_clientsession(self.hass, verify_ssl=False),
            port=effective_port,
            api_key=api_key,
            tls=tls,
        )

        try:
            async with async_timeout.timeout(TIMEOUT):
                await api.start()
                await api.client.call_method("printer.info")
                return True
        except Exception:
            return False
        finally:
            await api.stop()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        errors = _feature_errors(self.hass, user_input or {})
        if user_input is not None and not errors:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.options_schema(
                self.config_entry.options if user_input is None else user_input
            ),
            errors=errors,
        )

    @staticmethod
    def options_schema(options):
        """Share configuration between installation and later changes."""
        polling_rate = max(
            MIN_POLLING_RATE,
            options.get(CONF_OPTION_POLLING_RATE, DEFAULT_POLLING_RATE),
        )
        return vol.Schema(
            {
                vol.Optional(
                    CONF_OPTION_POLLING_RATE,
                    default=polling_rate,
                ): vol.All(int, vol.Range(min=MIN_POLLING_RATE)),
                vol.Optional(
                    CONF_OPTION_QUIET_UNREACHABLE,
                    default=options.get(CONF_OPTION_QUIET_UNREACHABLE, False),
                ): bool,
                vol.Optional(
                    CONF_OPTION_CAMERA_STREAM,
                    default=options.get(CONF_OPTION_CAMERA_STREAM, ""),
                ): str,
                vol.Optional(
                    CONF_OPTION_CAMERA_SNAPSHOT,
                    default=options.get(CONF_OPTION_CAMERA_SNAPSHOT, ""),
                ): str,
                vol.Optional(
                    CONF_OPTION_CAMERA_PORT,
                    default=options.get(CONF_OPTION_CAMERA_PORT, ""),
                ): str,
                vol.Optional(
                    CONF_OPTION_THUMBNAIL_PORT,
                    default=options.get(CONF_OPTION_THUMBNAIL_PORT, ""),
                ): str,
                vol.Optional(
                    CONF_OPTION_POWER_SENSOR,
                    description={
                        "suggested_value": options.get(CONF_OPTION_POWER_SENSOR)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class=SensorDeviceClass.POWER,
                    )
                ),
                vol.Optional(
                    CONF_OPTION_MAX_FLOW,
                    default=options.get(CONF_OPTION_MAX_FLOW, DEFAULT_MAX_FLOW_MM3),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=200)),
                vol.Optional(
                    CONF_OPTION_ENERGY_RATE,
                    default=options.get(CONF_OPTION_ENERGY_RATE, 0.0),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0)),
                vol.Optional(
                    CONF_OPTION_NOTIFY_SERVICE,
                    default=options.get(CONF_OPTION_NOTIFY_SERVICE, ""),
                ): str,
                vol.Optional(
                    CONF_OPTION_POWER_SWITCH,
                    description={
                        "suggested_value": options.get(CONF_OPTION_POWER_SWITCH)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Optional(
                    CONF_OPTION_POWER_OFF_DELAY,
                    default=options.get(
                        CONF_OPTION_POWER_OFF_DELAY,
                        DEFAULT_POWER_OFF_DELAY_MIN,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1440)),
                vol.Optional(
                    CONF_OPTION_POWER_OFF_MAX_TEMP,
                    default=options.get(
                        CONF_OPTION_POWER_OFF_MAX_TEMP,
                        DEFAULT_POWER_OFF_MAX_TEMP,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=120)),
                vol.Optional(
                    CONF_OPTION_AMBIENT_SENSOR,
                    description={
                        "suggested_value": options.get(CONF_OPTION_AMBIENT_SENSOR)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class=SensorDeviceClass.TEMPERATURE,
                    )
                ),
                vol.Optional(
                    CONF_OPTION_HUMIDITY_SENSOR,
                    description={
                        "suggested_value": options.get(CONF_OPTION_HUMIDITY_SENSOR)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class=SensorDeviceClass.HUMIDITY,
                    )
                ),
                vol.Optional(
                    CONF_OPTION_AI_TASK_ENTITY,
                    description={
                        "suggested_value": options.get(CONF_OPTION_AI_TASK_ENTITY)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="ai_task")
                ),
                vol.Optional(
                    CONF_OPTION_VISION_CAMERA,
                    description={
                        "suggested_value": options.get(CONF_OPTION_VISION_CAMERA)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="camera")
                ),
                vol.Optional(
                    CONF_OPTION_PANEL_ROLE,
                    default=(options.get(CONF_OPTION_PANEL_ROLE, "admin_only")),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["admin_only", "operator"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="panel_role",
                    )
                ),
            }
        )
