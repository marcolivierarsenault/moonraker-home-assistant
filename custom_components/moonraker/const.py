"""Constants for Moonraker."""
from homeassistant.const import Platform

# Base component constants
DOMAIN = "moonraker"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.4.0"
MANIFACTURER = "@marcolivierarsenault"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.CAMERA]

CONF_API_KEY = "api_key"
CONF_URL = "url"
CONF_PORT = "port"

# API dict keys
HOSTNAME = "hostname"
OBJ = "objects"
