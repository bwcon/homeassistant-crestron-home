"""The Crestron Home integration."""
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_PROTOCOL, CONF_SSL_VERIFY, DOMAIN, PLATFORMS
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

    coordinator = CrestronHomeDataUpdateCoordinator(hass, api)

    # Perform first update to populate coordinator data and room list
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator instance
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # We can clean up api resources if needed
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Note: session is managed by HA's aiohttp client, so we do not close it manually here.

    return unload_ok
