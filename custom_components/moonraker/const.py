"""Constants for Moonraker."""
from homeassistant.const import Platform

# Base component constants
DOMAIN = "moonraker"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.2.0"
MANIFACTURER = "@marcolivierarsenault"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.CAMERA]

CONF_URL = "url"
CONF_PORT = "port"

# API dict keys

OBJ = "objects"
