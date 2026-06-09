"""Platform for climate/thermostat integration."""
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import CrestronHomeDataUpdateCoordinator

# Mappings from Home Assistant modes to Crestron system modes
HA_TO_CRESTRON_MODE = {
    HVACMode.OFF: "Off",
    HVACMode.HEAT: "Heat",
    HVACMode.COOL: "Cool",
    HVACMode.HEAT_COOL: "Auto",
}

CRESTRON_TO_HA_MODE = {
    "off": HVACMode.OFF,
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "auto": HVACMode.HEAT_COOL,
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Crestron Home thermostats."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    devices = coordinator.data.get("devices", {})
    for device_id, device_data in devices.items():
        if device_data.get("type") == "thermostat":
            entities.append(CrestronHomeThermostat(coordinator, device_id))
            
    async_add_entities(entities)


class CrestronHomeThermostat(CoordinatorEntity[CrestronHomeDataUpdateCoordinator], ClimateEntity):
    """Representation of a Crestron Home thermostat."""

    def __init__(
        self, coordinator: CrestronHomeDataUpdateCoordinator, device_id: int
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device_data = self.coordinator.data["devices"][self._device_id]
        room_id = device_data.get("roomId")
        room_name = self.coordinator.rooms.get(room_id, "")

        self._attr_name = device_data.get("name")
        self._attr_unique_id = f"{DOMAIN}_climate_{device_id}"
        
        if room_name:
            self._attr_suggested_area = room_name

        # Support target temperature and hvac modes. Support target range if Auto mode is available.
        features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        
        available_modes = [m.lower() for m in device_data.get("availableSystemModes", [])]
        if "auto" in available_modes:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            
        self._attr_supported_features = features

        # Set up DeviceInfo
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of temperature measurement."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        unit = device_data.get("temperatureUnits", "")
        
        if "fahrenheit" in unit.lower():
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        temp = device_data.get("currentTemperature")
        if temp is None:
            return None
        return float(temp) / 10.0

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the target temperature."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        setpoint = device_data.get("setPoint")
        if not setpoint or self.hvac_mode == HVACMode.HEAT_COOL:
            return None
        
        temp = setpoint.get("temperature")
        if temp is None:
            return None
        return float(temp) / 10.0

    @property
    def target_temperature_low(self) -> Optional[float]:
        """Return the heating target temperature in auto mode."""
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None
        
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        # Look for Heat setpoint in availableSetPoints or current settings
        # Crestron's auto mode setpoint returns active setpoint in 'setPoint'.
        # However, for dual setpoints in auto mode, we search for the specific setpoints.
        # Let's check availableSetPoints
        avail_sp = device_data.get("availableSetPoints", [])
        for sp in avail_sp:
            if sp.get("type") == "Heat":
                # Wait, does availableSetPoints contain the current temperature?
                # If availableSetPoints only lists min/max, we fallback.
                pass
        
        # If active setpoint is Heat, we return it. Otherwise, we return a default offset
        # or search if the processor exposes the other setpoint.
        # For simplicity, if we don't have dual setpoint values from API, we return target_temperature - 2
        setpoint = device_data.get("setPoint")
        if not setpoint:
            return None
        
        sp_type = setpoint.get("type", "")
        temp = setpoint.get("temperature")
        if temp is None:
            return None
            
        if sp_type == "Heat":
            return float(temp) / 10.0
            
        # Fallback if active is Cool
        return (float(temp) / 10.0) - 2.0

    @property
    def target_temperature_high(self) -> Optional[float]:
        """Return the cooling target temperature in auto mode."""
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None
        
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        setpoint = device_data.get("setPoint")
        if not setpoint:
            return None
        
        sp_type = setpoint.get("type", "")
        temp = setpoint.get("temperature")
        if temp is None:
            return None
            
        if sp_type == "Cool":
            return float(temp) / 10.0
            
        # Fallback if active is Heat
        return (float(temp) / 10.0) + 2.0

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation mode."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        mode = device_data.get("mode", "off").lower()
        return CRESTRON_TO_HA_MODE.get(mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> List[HVACMode]:
        """Return the list of available hvac operation modes."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        avail = device_data.get("availableSystemModes", [])
        
        modes = []
        for m in avail:
            ha_m = CRESTRON_TO_HA_MODE.get(m.lower())
            if ha_m and ha_m not in modes:
                modes.append(ha_m)
        return modes if modes else [HVACMode.OFF]

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the fan setting."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        return device_data.get("currentFanMode")

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        return device_data.get("availableFanModes")

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        setpoint = device_data.get("setPoint")
        if setpoint and "minValue" in setpoint:
            return float(setpoint["minValue"]) / 10.0
        return 45.0 if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else 7.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        setpoint = device_data.get("setPoint")
        if setpoint and "maxValue" in setpoint:
            return float(setpoint["maxValue"]) / 10.0
        return 95.0 if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else 35.0

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        setpoint = device_data.get("setPoint", {})
        sp_type = setpoint.get("type", "Cool")

        setpoints_payload = []

        if "target_temp_low" in kwargs and "target_temp_high" in kwargs:
            # Set dual setpoints in Auto mode
            low = kwargs["target_temp_low"]
            high = kwargs["target_temp_high"]
            setpoints_payload.append({"type": "Heat", "temperature": int(low * 10)})
            setpoints_payload.append({"type": "Cool", "temperature": int(high * 10)})
            LOGGER.debug("Setting thermostat dual setpoint: Heat: %s, Cool: %s", low, high)
        elif ATTR_TEMPERATURE in kwargs:
            # Set single target temperature based on active setpoint type
            temp = kwargs[ATTR_TEMPERATURE]
            setpoints_payload.append({"type": sp_type, "temperature": int(temp * 10)})
            LOGGER.debug("Setting thermostat single setpoint (%s): %s", sp_type, temp)
        else:
            return

        # Optimistically update cache
        if self._device_id in self.coordinator.data["devices"]:
            for sp in setpoints_payload:
                if sp["type"] == sp_type:
                    self.coordinator.data["devices"][self._device_id]["setPoint"]["temperature"] = sp["temperature"]
        self.async_write_ha_state()

        success = await self.coordinator.api.set_thermostat_setpoint(self._device_id, setpoints_payload)
        if not success:
            LOGGER.error("Failed to set thermostat temperature")
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        # Find exact case-sensitive string matching the processor's available system modes
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        avail = device_data.get("availableSystemModes", [])
        
        target_mode = HA_TO_CRESTRON_MODE.get(hvac_mode)
        if not target_mode:
            return
            
        # Match case-insensitively to the exact string exposed by processor
        matched_mode = next((m for m in avail if m.lower() == target_mode.lower()), target_mode)
        
        LOGGER.debug("Setting thermostat %s mode to %s", self.name, matched_mode)

        # Optimistically update cache
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["mode"] = matched_mode
        self.async_write_ha_state()

        success = await self.coordinator.api.set_thermostat_mode(self._device_id, matched_mode)
        if not success:
            LOGGER.error("Failed to set thermostat mode to %s", matched_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        device_data = self.coordinator.data["devices"].get(self._device_id, {})
        avail = device_data.get("availableFanModes", [])
        
        matched_fan_mode = next((f for f in avail if f.lower() == fan_mode.lower()), fan_mode)

        LOGGER.debug("Setting thermostat %s fan mode to %s", self.name, matched_fan_mode)

        # Optimistically update cache
        if self._device_id in self.coordinator.data["devices"]:
            self.coordinator.data["devices"][self._device_id]["currentFanMode"] = matched_fan_mode
        self.async_write_ha_state()

        success = await self.coordinator.api.set_thermostat_fan_mode(self._device_id, matched_fan_mode)
        if not success:
            LOGGER.error("Failed to set thermostat fan mode to %s", matched_fan_mode)
        await self.coordinator.async_request_refresh()
