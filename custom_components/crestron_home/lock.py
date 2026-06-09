"""Platform for lock integration."""
from typing import Any, Optional

from homeassistant.components.lock import LockEntity
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
    """Set up the Crestron Home door locks."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Check both coordinator.data["doorlocks"] and coordinator.data["devices"] (in case locks are returned in either)
    lock_ids = set()
    
    doorlocks = coordinator.data.get("doorlocks", {})
    for lock_id, lock_data in doorlocks.items():
        entities.append(CrestronHomeLock(coordinator, lock_id, is_manned_endpoint=True))
        lock_ids.add(lock_id)

    devices = coordinator.data.get("devices", {})
    for device_id, device_data in devices.items():
        if device_data.get("type") == "lock" and device_id not in lock_ids:
            entities.append(CrestronHomeLock(coordinator, device_id, is_manned_endpoint=False))
            lock_ids.add(device_id)
            
    async_add_entities(entities)


class CrestronHomeLock(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], LockEntity):
    """Representation of a Crestron Home door lock."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int, is_manned_endpoint: bool
    ) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._is_manned_endpoint = is_manned_endpoint
        
        # Get data source
        data_source = "doorlocks" if is_manned_endpoint else "devices"
        lock_data = self.coordinator.data[data_source][self._device_id]
        room_id = lock_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = lock_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_lock_{device_id}"
        
        if room_name:
            self._attr_suggested_area = room_name

        # Set up DeviceInfo
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def is_locked(self) -> Optional[bool]:
        """Return true if lock is locked."""
        data_source = "doorlocks" if self._is_manned_endpoint else "devices"
        lock_data = self.coordinator.data[data_source].get(self._device_id, {})
        
        # Check standard state fields
        state = lock_data.get("state", "").lower()
        status = lock_data.get("status", "").lower()
        door_lock_status = lock_data.get("lock status", "").lower() or lock_data.get("doorLockStatus", "").lower()
        
        # Support various string representations
        if "unlocked" in (state, status, door_lock_status):
            return False
        if "locked" in (state, status, door_lock_status):
            return True
            
        return None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door."""
        LOGGER.debug("Locking door %s (ID: %s)", self.name, self._device_id)
        
        # Optimistic update
        data_source = "doorlocks" if self._is_manned_endpoint else "devices"
        if self._device_id in self.coordinator.data[data_source]:
            self.coordinator.data[data_source][self._device_id]["state"] = "Locked"
        self.async_write_ha_state()

        success = await self.coordinator.api.lock_door(self._device_id)
        if not success:
            LOGGER.error("Failed to lock door %s", self.name)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door."""
        LOGGER.debug("Unlocking door %s (ID: %s)", self.name, self._device_id)
        
        # Optimistic update
        data_source = "doorlocks" if self._is_manned_endpoint else "devices"
        if self._device_id in self.coordinator.data[data_source]:
            self.coordinator.data[data_source][self._device_id]["state"] = "Unlocked"
        self.async_write_ha_state()

        success = await self.coordinator.api.unlock_door(self._device_id)
        if not success:
            LOGGER.error("Failed to unlock door %s", self.name)
        await self.coordinator.async_request_refresh()
