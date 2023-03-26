"""Constants for Moonraker."""
from enum import Enum

from homeassistant.const import Platform

# Base component constants
DOMAIN = "moonraker"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.6.0"
MANIFACTURER = "@marcolivierarsenault"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.CAMERA, Platform.BUTTON]

CONF_API_KEY = "api_key"
CONF_URL = "url"
CONF_PORT = "port"

# API dict keys
HOSTNAME = "hostname"
OBJ = "objects"


class METHODS(Enum):
    """API methods."""

    SERVER_FILES_METADATA = "server.files.metadata"
    SERVER_HISTORY_TOTALS = "server.history.totals"
    SERVER_WEBCAMS_LIST = "server.webcams.list"
    PRINTER_EMERGENCY_STOP = "printer.emergency_stop"
    PRINTER_GCODE_HELP = "printer.gcode.help"
    PRINTER_GCODE_SCRIPT = "printer.gcode.script"
    PRINTER_INFO = "printer.info"
    PRINTER_OBJECTS_LIST = "printer.objects.list"
    PRINTER_OBJECTS_QUERY = "printer.objects.query"


class ExtendedEnum(Enum):
    """Extended Enum class."""

    @classmethod
    def list(cls):
        """Return a list of all enum values."""
        return list(map(lambda c: c.value, cls))


class PRINTSTATES(ExtendedEnum):
    """Printer state."""

    STANDBY = "standby"
    PRINTING = "printing"
    PAUSED = "paused"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"


class PRINTERSTATES(ExtendedEnum):
    """Printer state."""

    READY = "ready"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    ERROR = "error"
