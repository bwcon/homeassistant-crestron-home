"""Constants for the Crestron Home integration."""
import logging

DOMAIN = "crestron_home"
LOGGER = logging.getLogger(__package__)

# Configuration keys
CONF_SSL_VERIFY = "ssl_verify"
CONF_PROTOCOL = "protocol"
CONF_KEYPAD_BRIDGE_HOST = "keypad_bridge_host"
CONF_KEYPAD_BRIDGE_PORT = "keypad_bridge_port"

# Default values
DEFAULT_PORT = 443
DEFAULT_PROTOCOL = "https"
DEFAULT_SCAN_INTERVAL = 15  # seconds
DEFAULT_KEYPAD_BRIDGE_PORT = 9008

# Event types
EVENT_CRESTRON_KEYPAD = "crestron_keypad_event"

# Platforms to load
PLATFORMS = [
    "light",
    "cover",
    "climate",
    "scene",
    "lock",
    "sensor",
    "binary_sensor",
    "event",
]

