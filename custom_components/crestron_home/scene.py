"""Platform for scene integration."""
from typing import Any

from homeassistant.components.scene import Scene
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
    """Set up the Crestron Home scenes."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    scenes = coordinator.data.get("scenes", {})
    for scene_id, scene_data in scenes.items():
        entities.append(CrestronHomeScene(coordinator, scene_id))
            
    async_add_entities(entities)


class CrestronHomeScene(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], Scene):
    """Representation of a Crestron Home scene."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, scene_id: int
    ) -> None:
        """Initialize the scene."""
        super().__init__(coordinator)
        self._scene_id = scene_id
        
        scene_data = self.coordinator.data["scenes"][self._scene_id]
        room_id = scene_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = scene_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_scene_{scene_id}"
        
        if room_name:
            self._attr_suggested_area = room_name

        # Set up DeviceInfo
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene."""
        LOGGER.debug("Recalling scene %s (ID: %s)", self.name, self._scene_id)
        success = await self.coordinator.api.recall_scene(self._scene_id)
        if not success:
            LOGGER.error("Failed to recall scene %s", self.name)
        
        # Scenes are fire-and-forget, but we trigger a coordinator update to fetch modified states
        await self.coordinator.async_request_refresh()
