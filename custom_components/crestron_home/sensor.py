"""Platform for sensor integration."""
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, LIGHT_LUX
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
    """Set up the Crestron Home sensors."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    devices = coordinator.data.get("devices", {})
    for device_id, device_data in devices.items():
        if device_data.get("type") == "sensor":
            subtype = device_data.get("subType", "")
            
            # Illuminance sensor
            if subtype == "PhotoSensor" or "level" in device_data:
                entities.append(CrestronHomeIlluminanceSensor(coordinator, device_id))
                
            # Battery sensor
            if "battery level" in device_data or "battery" in device_data or "batteryLevel" in device_data:
                entities.append(CrestronHomeBatterySensor(coordinator, device_id))
                
    async_add_entities(entities)


class CrestronHomeIlluminanceSensor(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], SensorEntity):
    """Representation of a Crestron Home Photo/Light sensor."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = f"{device_data.get('name')} Light Level"
        self._attr_unique_id = f"{DOMAIN}_sensor_lux_{device_id}"
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = LIGHT_LUX
        
        if room_name:
            self._attr_suggested_area = room_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current illuminance value."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        return device_data.get("level")


class CrestronHomeBatterySensor(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], SensorEntity):
    """Representation of a Crestron Home device battery level."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = f"{device_data.get('name')} Battery"
        self._attr_unique_id = f"{DOMAIN}_sensor_battery_{device_id}"
        self._attr_device_class = SensorDeviceClass.BATTERY
        
        if room_name:
            self._attr_suggested_area = room_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def native_value(self) -> Optional[Any]:
        """Return the battery status or percentage."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        # Can be battery level (e.g. "Normal") or battery percentage (integer)
        val = device_data.get("battery level") or device_data.get("battery") or device_data.get("batteryLevel")
        return val

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        """Return unit of measurement if value is numeric."""
        val = self.native_value
        if isinstance(val, (int, float)):
            return PERCENTAGE
        return None
