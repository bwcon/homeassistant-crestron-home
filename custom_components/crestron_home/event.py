"""Event platform for Crestron Home keypad button presses.

This platform creates EventEntity instances for each keypad event channel
discovered from the Keypad Event Bridge driver. Events are triggered by the
coordinator polling the bridge's HTTP endpoint.

Users can trigger automations on these events using the standard HA event
entity triggers, or use the companion automation blueprint.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_KEYPAD_BRIDGE_HOST,
    DOMAIN,
    EVENT_CRESTRON_KEYPAD,
    LOGGER,
)
from .coordinator import CrestronHomeDataUpdateCoordinator

# Maximum number of channels to create entities for.
# Matches the max configurable in the Crestron driver (32).
MAX_CHANNELS = 32

# Event types that the Crestron driver can fire
KEYPAD_EVENT_TYPES = ["tap", "double_tap", "hold", "release"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Crestron Home keypad event entities."""
    coordinator: CrestronHomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Only create event entities if the keypad bridge is configured
    bridge_host = entry.data.get(CONF_KEYPAD_BRIDGE_HOST, "").strip()
    if not bridge_host:
        LOGGER.debug("Keypad bridge not configured — skipping event platform")
        return

    # Try to detect how many channels the bridge has via /health
    channel_count = await _detect_channel_count(hass, coordinator)

    entities = []
    for channel_num in range(1, channel_count + 1):
        entities.append(
            CrestronKeypadEventEntity(coordinator, entry, channel_num)
        )

    LOGGER.info(
        "Setting up %d Crestron keypad event entities", len(entities)
    )
    async_add_entities(entities)


async def _detect_channel_count(
    hass: HomeAssistant,
    coordinator: CrestronHomeDataUpdateCoordinator,
) -> int:
    """Query the keypad bridge /health endpoint to get the channel count."""
    if not coordinator._keypad_bridge_url:
        return 16  # default

    import aiohttp

    try:
        url = f"{coordinator._keypad_bridge_url}/health"
        session = hass.helpers.aiohttp_client.async_get_clientsession(
            hass, verify_ssl=False
        )
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                count = data.get("channels", 16)
                LOGGER.debug("Keypad bridge reports %d channels", count)
                return min(count, MAX_CHANNELS)
    except Exception:  # noqa: BLE001
        LOGGER.debug("Could not reach keypad bridge /health — defaulting to 16 channels")

    return 16


class CrestronKeypadEventEntity(CoordinatorEntity, EventEntity):
    """Represents a single keypad event channel from the Crestron Event Bridge.

    Each entity corresponds to one Event Channel on the Crestron driver.
    When the coordinator detects a new event for this channel, it triggers
    the HA event entity.
    """

    _attr_has_entity_name = True
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = KEYPAD_EVENT_TYPES

    def __init__(
        self,
        coordinator: CrestronHomeDataUpdateCoordinator,
        entry: ConfigEntry,
        channel_num: int,
    ) -> None:
        """Initialize the keypad event entity."""
        super().__init__(coordinator)
        self._channel_num = channel_num
        self._entry_id = entry.entry_id

        self._attr_unique_id = f"{entry.entry_id}_keypad_ch_{channel_num}"
        self._attr_name = f"Keypad Channel {channel_num}"

    @property
    def device_info(self):
        """Return device info to group all keypad channels under one device."""
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_keypad_bridge")},
            "name": "Crestron Keypad Event Bridge",
            "manufacturer": "BW Consulting",
            "model": "Keypad Event Bridge",
            "sw_version": "1.0.0",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Check if there are new keypad events for this channel and trigger them.
        """
        if not self.coordinator.data:
            return

        keypad_events = self.coordinator.data.get("keypad_events", [])
        for event in keypad_events:
            if event.get("channel") == self._channel_num:
                # Map Crestron action names to HA event types
                action = event.get("action", "").lower()
                event_type = _map_action_to_event_type(action)
                if event_type:
                    self._trigger_event(
                        event_type,
                        {
                            "channel": self._channel_num,
                            "channel_name": event.get("channelName", ""),
                            "raw_action": event.get("action", ""),
                            "timestamp": event.get("timestamp", ""),
                        },
                    )

        self.async_write_ha_state()


def _map_action_to_event_type(action: str) -> str | None:
    """Map Crestron driver action names to HA event entity types."""
    mapping = {
        "tap": "tap",
        "doubletap": "double_tap",
        "hold": "hold",
        "release": "release",
    }
    return mapping.get(action.lower().replace("_", ""))
