"""Constants for integration_blueprint tests."""
from custom_components.moonraker.const import (
    CONF_API_KEY,
    CONF_PORT,
    CONF_PRINTER_NAME,
    CONF_TLS,
    CONF_URL,
    CONF_OPTION_CAMERA_STREAM,
    CONF_OPTION_CAMERA_SNAPSHOT,
)

# Mock config data to be used across multiple tests
MOCK_CONFIG = {
    CONF_URL: "1.2.3.4",
    CONF_PORT: "1234",
    CONF_TLS: False,
    CONF_API_KEY: "",
    CONF_PRINTER_NAME: "",
}

MOCK_OPTIONS = {
    CONF_OPTION_CAMERA_STREAM: "http://1.2.3.4/stream",
    CONF_OPTION_CAMERA_SNAPSHOT: "http://1.2.3.4/snapshot",
}

MOCK_CONFIG_WITH_NAME = {
    CONF_URL: "1.2.3.4",
    CONF_PORT: "1234",
    CONF_TLS: False,
    CONF_API_KEY: "",
    CONF_PRINTER_NAME: "example name",
}
