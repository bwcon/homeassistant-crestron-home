"""Platform for binary sensor integration."""
from typing import Any, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    """Set up the Crestron Home binary sensors."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    devices = coordinator.data.get("devices", {})
    for device_id, device_data in devices.items():
        if device_data.get("type") == "sensor":
            subtype = device_data.get("subType", "")
            
            # Occupancy / Presence Sensor
            if subtype == "OccupancySensor" or "presence" in device_data:
                entities.append(CrestronHomeOccupancySensor(coordinator, device_id))
                
            # Door / Contact Sensor
            if subtype == "DoorSensor" or "door status" in device_data or "doorStatus" in device_data:
                entities.append(CrestronHomeDoorSensor(coordinator, device_id))
                
    async_add_entities(entities)


class CrestronHomeOccupancySensor(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a Crestron Home occupancy sensor."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = device_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_binary_sensor_occupancy_{device_id}"
        self._attr_device_class = BinarySensorDeviceClass.OCCUPANCY
        
        if room_name:
            self._attr_suggested_area = room_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def is_on(self) -> bool:
        """Return true if occupancy is detected."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        presence = device_data.get("presence", "").lower()
        state = device_data.get("state", "").lower()
        
        return "occupied" in (presence, state) or "active" in (presence, state) or presence == "on"


class CrestronHomeDoorSensor(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a Crestron Home door contact sensor."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = device_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_binary_sensor_door_{device_id}"
        self._attr_device_class = BinarySensorDeviceClass.DOOR
        
        if room_name:
            self._attr_suggested_area = room_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def is_on(self) -> bool:
        """Return true if door is open."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        status = (device_data.get("door status") or device_data.get("doorStatus") or device_data.get("status") or "").lower()
        
        return "open" in status or "opened" in status
