"""Adds config flow for Moonraker."""
import logging

from homeassistant import config_entries
import voluptuous as vol

from .const import CONF_API_KEY, CONF_PORT, CONF_URL, DOMAIN

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
            if not await self._test_connection(user_input[CONF_URL]):
                self._errors[CONF_URL] = "error"
                return await self._show_config_form(user_input)

            if not await self._test_port(user_input[CONF_PORT]):
                self._errors[CONF_PORT] = "port_error"
                return await self._show_config_form(user_input)

            if not await self._test_api_key(user_input[CONF_API_KEY]):
                self._errors[CONF_API_KEY] = "api_key_error"
                return await self._show_config_form(user_input)

            # changer DOMAIN pour name
            return self.async_create_entry(title=DOMAIN, data=user_input)

        user_input = {}
        # Provide defaults for form
        user_input[CONF_URL] = "192.168.1.123"
        user_input[CONF_PORT] = "7125"
        user_input[CONF_API_KEY] = ""

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit location data."""

        _LOGGER.debug("Showing moonraker conf")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=user_input[CONF_URL]): str,
                    vol.Optional(CONF_PORT, default=user_input[CONF_PORT]): str,
                    vol.Optional(CONF_API_KEY, default=user_input[CONF_API_KEY]): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_connection(self, _url):
        """Return true if connection is valid."""
        # Test connection and get hostname
        # await api.client.call_method("printer.info")
        # printer_info[HOSTNAME]
        self.title = DOMAIN  # TODO change for hostname
        return True

    async def _test_port(self, port):
        if not port == "":
            if not port.isdigit() or int(port) > 65535 or int(port) <= 1024:
                return False
        return True

    async def _test_api_key(self, api_key):
        if not api_key == "":
            if not api_key.isalnum() or len(api_key) != 32:
                return False
        return True
