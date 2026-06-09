"""DataUpdateCoordinator for Crestron Home."""
import asyncio
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER
from .api import CrestronHomeAPI, CrestronHomeAPIError

class CrestronHomeDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Crestron Home data from processor."""

    def __init__(self, hass: HomeAssistant, api: CrestronHomeAPI) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.rooms: Dict[int, str] = {}
        
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Crestron Home REST API endpoints."""
        try:
            # Load room mapping if it hasn't been loaded yet
            if not self.rooms:
                rooms_list = await self.api.get_rooms()
                self.rooms = {room["id"]: room["name"] for room in rooms_list}
                LOGGER.debug("Loaded room definitions: %s", self.rooms)

            # Poll endpoints in parallel
            # Wrap in safe calls to avoid failing the whole update if an endpoint is unsupported
            async def get_devices_safe():
                try:
                    return await self.api.get_devices()
                except Exception as err:
                    LOGGER.error("Error fetching devices: %s", err)
                    raise err

            async def get_scenes_safe():
                try:
                    return await self.api.get_scenes()
                except Exception as err:
                    LOGGER.debug("Could not fetch scenes (may not be configured): %s", err)
                    return []

            async def get_doorlocks_safe():
                try:
                    return await self.api.get_doorlocks()
                except Exception as err:
                    LOGGER.debug("Could not fetch door locks (may not be configured): %s", err)
                    return []

            LOGGER.debug("Polling Crestron Home processor state")
            devices_list, scenes_list, doorlocks_list = await asyncio.gather(
                get_devices_safe(),
                get_scenes_safe(),
                get_doorlocks_safe(),
            )

            # Convert lists to dictionaries indexed by ID for easy lookup in entities
            devices_dict = {device["id"]: device for device in devices_list}
            scenes_dict = {scene["id"]: scene for scene in scenes_list}
            doorlocks_dict = {lock["id"]: lock for lock in doorlocks_list}

            return {
                "devices": devices_dict,
                "scenes": scenes_dict,
                "doorlocks": doorlocks_dict,
            }
            
        except CrestronHomeAPIError as err:
            raise UpdateFailed(f"Error communicating with Crestron API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error updating Crestron Home data: {err}") from err
