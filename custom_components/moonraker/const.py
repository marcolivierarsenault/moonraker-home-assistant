"""Constants for Moonraker."""
from enum import Enum

from homeassistant.const import Platform

# Base component constants
DOMAIN = "moonraker"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.5.0"
MANIFACTURER = "@marcolivierarsenault"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.CAMERA, Platform.BUTTON]

CONF_API_KEY = "api_key"
CONF_URL = "url"
CONF_PORT = "port"

# API dict keys
HOSTNAME = "hostname"
OBJ = "objects"


class METHOD(Enum):
    """API methods."""

    SERVER_FILES_METADATA = "server.files.metadata"
    SERVER_WEBCAMS_LIST = "server.webcams.list"
    PRINTER_EMERGENCY_STOP = "printer.emergency_stop"
    PRINTER_GCODE_HELP = "printer.gcode.help"
    PRINTER_GCODE_SCRIPT = "printer.gcode.script"
    PRINTER_INFO = "printer.info"
    PRINTER_OBJECTS_LIST = "printer.objects.list"
    PRINTER_OBJECTS_QUERY = "printer.objects.query"

    def __str__(self):
        """Return the method name."""
        return self.value
