"""The Crestron Home integration."""
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_KEYPAD_BRIDGE_HOST,
    CONF_KEYPAD_BRIDGE_PORT,
    CONF_PROTOCOL,
    CONF_SSL_VERIFY,
    DEFAULT_KEYPAD_BRIDGE_PORT,
    DOMAIN,
    PLATFORMS,
)
from .api import CrestronHomeAPI
from .coordinator import CrestronHomeDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crestron Home from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    protocol = entry.data[CONF_PROTOCOL]
    token = entry.data[CONF_TOKEN]
    ssl_verify = entry.data[CONF_SSL_VERIFY]

    session = async_get_clientsession(hass, verify_ssl=ssl_verify)

    api = CrestronHomeAPI(
        host=host,
        port=port,
        protocol=protocol,
        token=token,
        ssl_verify=ssl_verify,
        session=session,
    )

    # Build keypad bridge URL if configured
    keypad_bridge_url = None
    bridge_host = entry.data.get(CONF_KEYPAD_BRIDGE_HOST, "").strip()
    bridge_port = entry.data.get(CONF_KEYPAD_BRIDGE_PORT, DEFAULT_KEYPAD_BRIDGE_PORT)
    if bridge_host:
        keypad_bridge_url = f"http://{bridge_host}:{bridge_port}/cws/api/ha-keypad-events"

    coordinator = CrestronHomeDataUpdateCoordinator(
        hass, api, entry=entry, keypad_bridge_url=keypad_bridge_url
    )

    # Perform first update to populate coordinator data and room list
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator instance
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Listen for options updates (poll interval, endpoint toggles)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Forward setup to all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — apply new poll interval immediately."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_interval_from_options()
    # Force an immediate refresh with new settings
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # We can clean up api resources if needed
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Note: session is managed by HA's aiohttp client, so we do not close it manually here.

    return unload_ok
