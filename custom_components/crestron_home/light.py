"""Platform for light integration."""
from typing import Any, Dict, Optional

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
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
    """Set up the Crestron Home lights."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    devices = coordinator.data.get("devices", {})
    for device_id, device_data in devices.items():
        if device_data.get("type") == "light":
            entities.append(CrestronHomeLight(coordinator, device_id))
            
    async_add_entities(entities)


class CrestronHomeLight(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], LightEntity):
    """Representation of a Crestron Home light."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        # Get room name from coordinator
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = device_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_light_{device_id}"
        
        # Suggested area matches the Crestron room name
        if room_name:
            self._attr_suggested_area = room_name

        self._is_dimmer = device_data.get("subType") == "Dimmer"
        
        if self._is_dimmer:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

        # Set up DeviceInfo to group entities
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        level = device_data.get("level", 0)
        state = device_data.get("state")
        
        # Check level first, fallback to state
        if level > 0:
            return True
        return state == "on"

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of the light."""
        if not self._is_dimmer:
            return None
        
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        level = device_data.get("level", 0)
        
        # Scale 0-65535 to 0-255
        return int(level * 255 / 65535)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_BRIGHTNESS in kwargs:
            # Scale 0-255 to 0-65535
            brightness = kwargs[ATTR_BRIGHTNESS]
            level = int(brightness * 65535 / 255)
        else:
            level = 65535

        LOGGER.debug("Turning on light %s (ID: %s) to level %s", self.name, self._device_id, level)
        
        # Optimistically update the coordinator local cache state for instant UI responsiveness
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["level"] = level
            self.coordinator.data["devices"][self._device_id]["state"] = "on"
        self.async_write_ha_state()

        success = await self.coordinator.api.set_light_state(self._device_id, level)
        if not success:
            LOGGER.error("Failed to turn on light %s", self.name)
            # Revert optimistic update on failure by triggering coordinator refresh
            await self.coordinator.async_request_refresh()
        else:
            # Refresh coordinator to ensure state matches processor
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        LOGGER.debug("Turning off light %s (ID: %s)", self.name, self._device_id)

        # Optimistically update cache
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["level"] = 0
            self.coordinator.data["devices"][self._device_id]["state"] = "off"
        self.async_write_ha_state()

        success = await self.coordinator.api.set_light_state(self._device_id, 0)
        if not success:
            LOGGER.error("Failed to turn off light %s", self.name)
            await self.coordinator.async_request_refresh()
        else:
            await self.coordinator.async_request_refresh()
