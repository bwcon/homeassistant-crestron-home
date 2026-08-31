"""Constants for the Crestron Home integration."""
import logging

DOMAIN = "crestron_home"
LOGGER = logging.getLogger(__package__)

# Configuration keys (initial setup)
CONF_SSL_VERIFY = "ssl_verify"
CONF_PROTOCOL = "protocol"
CONF_KEYPAD_BRIDGE_HOST = "keypad_bridge_host"
CONF_KEYPAD_BRIDGE_PORT = "keypad_bridge_port"

# Options keys (reconfigurable at runtime)
CONF_SCAN_INTERVAL = "scan_interval"
CONF_POLL_LIGHTS = "poll_lights"
CONF_POLL_SHADES = "poll_shades"
CONF_POLL_THERMOSTATS = "poll_thermostats"
CONF_POLL_SENSORS = "poll_sensors"
CONF_POLL_SCENES = "poll_scenes"
CONF_POLL_DOORLOCKS = "poll_doorlocks"

# Default values
DEFAULT_PORT = 443
DEFAULT_PROTOCOL = "https"
DEFAULT_SCAN_INTERVAL = 30  # seconds (relaxed from 15)
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
