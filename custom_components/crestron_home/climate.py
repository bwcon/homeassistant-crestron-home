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

# ---------------------------------------------------------------------------
# Mode mappings — HA ↔ Crestron
# ---------------------------------------------------------------------------
# Crestron modes are PascalCase strings.  We normalise to lower-case for
# lookup but preserve the original string when sending commands back.

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
    "auxheat": HVACMode.HEAT,       # Emergency / auxiliary heat → Heat
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_setpoint(setpoints: List[Dict[str, Any]], sp_type: str) -> Optional[float]:
    """Return the temperature (in real degrees) for *sp_type* or None.

    *setpoints* is the ``currentSetPoint`` list from the CWS API, e.g.
    ``[{"type": "cool", "temperature": 720}]`` where temperature is in
    DeciFahrenheit / CelsiusHalfDegrees (i.e. value / 10).
    """
    for sp in setpoints:
        if sp.get("type", "").lower() == sp_type.lower():
            temp = sp.get("temperature")
            if temp is not None:
                return float(temp) / 10.0
    return None


def _setpoint_minmax(
    setpoints: List[Dict[str, Any]], key: str,
) -> Optional[float]:
    """Return min/max value across all setpoint entries, divided by 10."""
    values = [
        sp[key] for sp in setpoints
        if key in sp and sp[key] is not None
    ]
    if not values:
        return None
    func = min if key == "minValue" else max
    return float(func(values)) / 10.0


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

class CrestronHomeThermostat(
    CoordinatorEntity[CrestronHomeDataUpdateCoordinator], ClimateEntity
):
    """Representation of a Crestron Home thermostat."""

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        device_id: int,
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

        # Features — always support target temp + fan mode
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )

        available_modes = [
            m.lower()
            for m in device_data.get("availableSystemModes", [])
        ]
        if "auto" in available_modes:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

        self._attr_supported_features = features

        # DeviceInfo
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"processor_{coordinator.api.host}")},
            name="Crestron Home Processor",
            manufacturer="Crestron",
            model="System Processor",
        )

    # ----- helpers -----

    def _device(self) -> Dict[str, Any]:
        return self.coordinator.data["devices"].get(self._device_id, {})

    def _current_setpoints(self) -> List[Dict[str, Any]]:
        """Return the currentSetPoint list (may be empty)."""
        raw = self._device().get("currentSetPoint")
        if isinstance(raw, list):
            return raw
        # Fallback: legacy dict format ("setPoint": {...})
        legacy = self._device().get("setPoint")
        if isinstance(legacy, dict):
            return [legacy]
        return []

    # ----- properties -----

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of temperature measurement."""
        unit = self._device().get("temperatureUnits", "")
        if "fahrenheit" in unit.lower():
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current ambient temperature."""
        temp = self._device().get("currentTemperature")
        if temp is None:
            return None
        return float(temp) / 10.0

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC operation mode."""
        # CWS field: "currentMode" (PascalCase, e.g. "Cool")
        mode = self._device().get("currentMode", "").lower()
        if not mode:
            # Fallback to legacy field name
            mode = self._device().get("mode", "off").lower()
        return CRESTRON_TO_HA_MODE.get(mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> List[HVACMode]:
        """Return the list of available HVAC operation modes."""
        avail = self._device().get("availableSystemModes", [])
        modes: List[HVACMode] = []
        for m in avail:
            ha_m = CRESTRON_TO_HA_MODE.get(m.lower())
            if ha_m and ha_m not in modes:
                modes.append(ha_m)
        # Always include OFF
        if HVACMode.OFF not in modes:
            modes.insert(0, HVACMode.OFF)
        return modes if modes else [HVACMode.OFF]

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the single active setpoint (Heat-only or Cool-only modes)."""
        if self.hvac_mode == HVACMode.HEAT_COOL:
            return None  # dual setpoints → use high/low instead

        setpoints = self._current_setpoints()
        if not setpoints:
            return None

        # In single-mode, pick the setpoint whose type matches the mode,
        # or just take the first entry.
        mode_str = self._device().get("currentMode", "").lower()
        temp = _find_setpoint(setpoints, mode_str)
        if temp is not None:
            return temp
        # Fallback: first setpoint
        first = setpoints[0].get("temperature")
        return float(first) / 10.0 if first is not None else None

    @property
    def target_temperature_low(self) -> Optional[float]:
        """Return the heating setpoint in Auto / Heat-Cool mode."""
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None
        return _find_setpoint(self._current_setpoints(), "heat")

    @property
    def target_temperature_high(self) -> Optional[float]:
        """Return the cooling setpoint in Auto / Heat-Cool mode."""
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None
        return _find_setpoint(self._current_setpoints(), "cool")

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the current fan setting."""
        return self._device().get("currentFanMode")

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes."""
        return self._device().get("availableFanModes")

    @property
    def min_temp(self) -> float:
        """Return the minimum setpoint temperature."""
        val = _setpoint_minmax(self._current_setpoints(), "minValue")
        if val is not None:
            return val
        return 45.0 if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else 7.0

    @property
    def max_temp(self) -> float:
        """Return the maximum setpoint temperature."""
        val = _setpoint_minmax(self._current_setpoints(), "maxValue")
        if val is not None:
            return val
        return 95.0 if self.temperature_unit == UnitOfTemperature.FAHRENHEIT else 35.0

    # ----- commands -----

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature(s)."""
        setpoints_payload: List[Dict[str, Any]] = []

        if "target_temp_low" in kwargs and "target_temp_high" in kwargs:
            low = kwargs["target_temp_low"]
            high = kwargs["target_temp_high"]
            setpoints_payload.append({"type": "Heat", "temperature": int(low * 10)})
            setpoints_payload.append({"type": "Cool", "temperature": int(high * 10)})
            LOGGER.debug(
                "Setting thermostat dual setpoint: Heat=%s, Cool=%s", low, high
            )
        elif ATTR_TEMPERATURE in kwargs:
            temp = kwargs[ATTR_TEMPERATURE]
            # Determine active setpoint type from current mode
            mode = self._device().get("currentMode", "Cool")
            sp_type = mode if mode in ("Heat", "Cool") else "Cool"
            setpoints_payload.append(
                {"type": sp_type, "temperature": int(temp * 10)}
            )
            LOGGER.debug(
                "Setting thermostat single setpoint (%s): %s", sp_type, temp
            )
        else:
            return

        # Optimistic cache update
        device = self.coordinator.data["devices"].get(self._device_id)
        if device is not None:
            device["currentSetPoint"] = setpoints_payload
        self.async_write_ha_state()

        success = await self.coordinator.api.set_thermostat_setpoint(
            self._device_id, setpoints_payload
        )
        if not success:
            LOGGER.error("Failed to set thermostat temperature")
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        avail = self._device().get("availableSystemModes", [])
        target_mode = HA_TO_CRESTRON_MODE.get(hvac_mode)
        if not target_mode:
            return

        # Match case-insensitively to the exact string the processor exposes
        matched = next(
            (m for m in avail if m.lower() == target_mode.lower()), target_mode
        )
        LOGGER.debug("Setting thermostat %s mode to %s", self.name, matched)

        device = self.coordinator.data["devices"].get(self._device_id)
        if device is not None:
            device["currentMode"] = matched
        self.async_write_ha_state()

        success = await self.coordinator.api.set_thermostat_mode(
            self._device_id, matched
        )
        if not success:
            LOGGER.error("Failed to set thermostat mode to %s", matched)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        avail = self._device().get("availableFanModes", [])
        matched = next(
            (f for f in avail if f.lower() == fan_mode.lower()), fan_mode
        )
        LOGGER.debug(
            "Setting thermostat %s fan mode to %s", self.name, matched
        )

        device = self.coordinator.data["devices"].get(self._device_id)
        if device is not None:
            device["currentFanMode"] = matched
        self.async_write_ha_state()

        success = await self.coordinator.api.set_thermostat_fan_mode(
            self._device_id, matched
        )
        if not success:
            LOGGER.error("Failed to set thermostat fan mode to %s", matched)
        await self.coordinator.async_request_refresh()
