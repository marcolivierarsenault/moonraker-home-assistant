"""Adds config flow for Moonraker."""

import asyncio
import contextlib
import logging

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import network, slugify

from .api import MoonrakerApiClient, async_fetch_api_key
from .const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    DEFAULT_POLLING_RATE,
    DEFAULT_PORT,
    CONF_OPTION_POLLING_RATE,
    CONF_OPTION_QUIET_UNREACHABLE,
    CONF_OPTION_CAMERA_STREAM,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_PORT,
    CONF_OPTION_THUMBNAIL_PORT,
    DOMAIN,
    MIN_POLLING_RATE,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class MoonrakerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Moonraker."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        _LOGGER.debug("loading moonraker confFlowHandler")
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            if not await self._async_validate_input(user_input):
                return await self._show_config_form(user_input)

            # changer DOMAIN pour name
            return self.async_create_entry(title=DOMAIN, data=user_input)

        user_input = {}
        # Provide defaults for form
        user_input[CONF_URL] = "192.168.1.123"
        user_input[CONF_PORT] = "7125"
        user_input[CONF_TLS] = False
        user_input[CONF_API_KEY] = ""
        user_input[CONF_USERNAME] = ""
        user_input[CONF_PRINTER_NAME] = ""

        return await self._show_config_form(user_input)

    async def async_step_reconfigure(self, user_input=None):
        """Change the connection settings of an existing entry."""
        self._errors = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            if await self._async_validate_input(user_input):
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, **user_input}
                )
                # A loaded entry reloads through its update listener.
                if not entry.update_listeners:
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
            suggested_values = user_input
        else:
            suggested_values = {
                CONF_URL: entry.data.get(CONF_URL, ""),
                CONF_PORT: str(entry.data.get(CONF_PORT) or ""),
                CONF_TLS: entry.data.get(CONF_TLS, False),
                CONF_API_KEY: entry.data.get(CONF_API_KEY, ""),
                CONF_PRINTER_NAME: entry.data.get(CONF_PRINTER_NAME, ""),
            }

        # Suggested values instead of defaults, so cleared fields stay empty.
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_URL): str,
                        vol.Optional(CONF_PORT, default=""): str,
                        vol.Optional(CONF_TLS, default=False): bool,
                        vol.Optional(CONF_API_KEY, default=""): str,
                        vol.Optional(CONF_USERNAME, default=""): str,
                        vol.Optional(CONF_PASSWORD, default=""): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.PASSWORD)
                        ),
                        vol.Optional(CONF_PRINTER_NAME, default=""): str,
                    }
                ),
                suggested_values,
            ),
            errors=self._errors,
        )

    async def _async_validate_input(self, user_input) -> bool:
        """Validate the connection settings, storing errors in self._errors."""
        if not await self._test_host(user_input[CONF_URL]):
            self._errors[CONF_URL] = "host_error"
        elif not await self._test_port(user_input[CONF_PORT]):
            self._errors[CONF_PORT] = "port_error"
        elif not await self._test_api_key(user_input[CONF_API_KEY]):
            self._errors[CONF_API_KEY] = "api_key_error"
        elif not await self._async_login(user_input):
            self._errors[CONF_USERNAME] = "auth_error"
        elif not await self._test_printer_name(user_input[CONF_PRINTER_NAME]):
            self._errors[CONF_PRINTER_NAME] = "printer_name_error"
        elif not await self._test_connection(
            user_input[CONF_URL],
            user_input[CONF_PORT],
            user_input[CONF_API_KEY],
            user_input[CONF_TLS],
        ):
            self._errors[CONF_URL] = "printer_connection_error"
        return not self._errors

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
                    vol.Optional(CONF_API_KEY, default=user_input[CONF_API_KEY]): str,
                    vol.Optional(
                        CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")
                    ): str,
                    vol.Optional(CONF_PASSWORD, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
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

    async def _async_login(self, user_input) -> bool:
        """Swap entered credentials for the API key, keeping them out of the entry."""
        username = user_input.pop(CONF_USERNAME, "")
        password = user_input.pop(CONF_PASSWORD, "")
        if not username or user_input[CONF_API_KEY]:
            return True
        api_key = await self._fetch_api_key(user_input, username, password)
        if api_key is None:
            user_input[CONF_USERNAME] = username
            return False
        user_input[CONF_API_KEY] = api_key
        return True

    async def _fetch_api_key(self, user_input, username, password):
        port = user_input[CONF_PORT] or DEFAULT_PORT
        try:
            async with asyncio.timeout(TIMEOUT):
                return await async_fetch_api_key(
                    async_get_clientsession(self.hass),
                    user_input[CONF_URL],
                    port,
                    user_input[CONF_TLS],
                    username,
                    password,
                )
        except Exception:
            _LOGGER.debug("Moonraker login failed", exc_info=True)
            return None

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
            await api.start()
            async with asyncio.timeout(TIMEOUT):
                await api.client.call_method("printer.info")
                return True
        except Exception:
            return False
        finally:
            with contextlib.suppress(Exception):
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
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_OPTION_POLLING_RATE,
                        default=self.config_entry.options.get(
                            CONF_OPTION_POLLING_RATE, DEFAULT_POLLING_RATE
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLLING_RATE)),
                    vol.Optional(
                        CONF_OPTION_QUIET_UNREACHABLE,
                        default=self.config_entry.options.get(
                            CONF_OPTION_QUIET_UNREACHABLE, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_OPTION_CAMERA_STREAM,
                        default=self.config_entry.options.get(
                            CONF_OPTION_CAMERA_STREAM, ""
                        ),
                    ): str,
                    vol.Optional(
                        CONF_OPTION_CAMERA_SNAPSHOT,
                        default=self.config_entry.options.get(
                            CONF_OPTION_CAMERA_SNAPSHOT, ""
                        ),
                    ): str,
                    vol.Optional(
                        CONF_OPTION_CAMERA_PORT,
                        default=self.config_entry.options.get(
                            CONF_OPTION_CAMERA_PORT, ""
                        ),
                    ): str,
                    vol.Optional(
                        CONF_OPTION_THUMBNAIL_PORT,
                        default=self.config_entry.options.get(
                            CONF_OPTION_THUMBNAIL_PORT, ""
                        ),
                    ): str,
                }
            ),
        )
