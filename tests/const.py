"""Constants for integration_blueprint tests."""
from custom_components.moonraker.const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_URL,
)

# Mock config data to be used across multiple tests
MOCK_CONFIG = {
    CONF_URL: "1.2.3.4",
    CONF_PORT: "1234",
    CONF_API_KEY: "",
    CONF_PRINTER_NAME: "",
}

MOCK_CONFIG_WITH_NAME = {
    CONF_URL: "1.2.3.4",
    CONF_PORT: "1234",
    CONF_API_KEY: "",
    CONF_PRINTER_NAME: "example name",
}
