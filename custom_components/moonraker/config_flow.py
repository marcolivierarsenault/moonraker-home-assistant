"""Adds config flow for Moonraker."""
from homeassistant import config_entries
import voluptuous as vol

import logging

from .const import DOMAIN, CONF_URL


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
            valid = await self._test_connection(user_input[CONF_URL])
            if valid:
                return self.async_create_entry(
                    title=DOMAIN, data=user_input
                )  # changer DOMAIN pour name
            self._errors["base"] = "error"

            return await self._show_config_form(user_input)

        user_input = {}
        # Provide defaults for form
        user_input[CONF_URL] = "192.168.1.123"

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument

        _LOGGER.debug("Showing moonraker conf")
        """Show the configuration form to edit location data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=user_input[CONF_URL]): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_connection(self, url):
        """Return true if connection is valid."""
        return True
