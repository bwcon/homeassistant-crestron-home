"""Platform for cover/shade integration."""
from typing import Any, Optional

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import CrestronHomeDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Crestron Home covers."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    devices = coordinator.data.get("devices", {})
    for device_id, device_data in devices.items():
        if device_data.get("type") == "shade":
            entities.append(CrestronHomeCover(coordinator, device_id))
            
    async_add_entities(entities)


class CrestronHomeCover(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], CoverEntity):
    """Representation of a Crestron Home shade."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        # Get room name from coordinator
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = device_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_cover_{device_id}"
        self._attr_device_class = CoverDeviceClass.SHADE
        
        if room_name:
            self._attr_suggested_area = room_name

        # Define supported features
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
        )

        # Set up DeviceInfo to group entities
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def current_cover_position(self) -> Optional[int]:
        """Return current position of cover. 0 is closed, 100 is open."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        position = device_data.get("position", 0)
        
        # Scale 0-65535 to 0-100% open
        return int(position * 100 / 65535)

    @property
    def is_closed(self) -> Optional[bool]:
        """Return if the cover is closed."""
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (100% position = 65535)."""
        LOGGER.debug("Opening cover %s (ID: %s)", self.name, self._device_id)
        
        # Optimistic update
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["position"] = 65535
        self.async_write_ha_state()

        success = await self.coordinator.api.set_shade_position(self._device_id, 65535)
        if not success:
            LOGGER.error("Failed to open cover %s", self.name)
            await self.coordinator.async_request_refresh()
        else:
            await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (0% position = 0)."""
        LOGGER.debug("Closing cover %s (ID: %s)", self.name, self._device_id)
        
        # Optimistic update
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["position"] = 0
        self.async_write_ha_state()

        success = await self.coordinator.api.set_shade_position(self._device_id, 0)
        if not success:
            LOGGER.error("Failed to close cover %s", self.name)
            await self.coordinator.async_request_refresh()
        else:
            await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position (0-100% open)."""
        position = kwargs["position"]
        level = int(position * 65535 / 100)
        
        LOGGER.debug("Setting cover %s (ID: %s) to position %s%% (level %s)", self.name, self._device_id, position, level)
        
        # Optimistic update
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["position"] = level
        self.async_write_ha_state()

        success = await self.coordinator.api.set_shade_position(self._device_id, level)
        if not success:
            LOGGER.error("Failed to set cover position %s", self.name)
            await self.coordinator.async_request_refresh()
        else:
            await self.coordinator.async_request_refresh()
