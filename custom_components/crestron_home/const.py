"""Constants for the Crestron Home integration."""
import logging

DOMAIN = "crestron_home"
LOGGER = logging.getLogger(__package__)

# Configuration keys
CONF_SSL_VERIFY = "ssl_verify"
CONF_PROTOCOL = "protocol"

# Default values
DEFAULT_PORT = 443
DEFAULT_PROTOCOL = "https"
DEFAULT_SCAN_INTERVAL = 15  # seconds

# Platforms to load
PLATFORMS = [
    "light",
    "cover",
    "climate",
    "scene",
    "lock",
    "sensor",
    "binary_sensor",
]
