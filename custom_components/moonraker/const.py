"""Constants for Moonraker."""
from homeassistant.const import Platform

# Base component constants
NAME = "Moonraker"
DOMAIN = "moonraker"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.1.0"
MANIFACTURER = "@marcolivierarsenault"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.CAMERA]

CONF_URL = "url"
