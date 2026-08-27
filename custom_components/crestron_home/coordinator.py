"""DataUpdateCoordinator for Crestron Home."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_CRESTRON_KEYPAD,
    LOGGER,
)
from .api import CrestronHomeAPI, CrestronHomeAPIError


class CrestronHomeDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Crestron Home data from processor."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CrestronHomeAPI,
        keypad_bridge_url: Optional[str] = None,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.rooms: Dict[int, str] = {}
        self._keypad_bridge_url = keypad_bridge_url
        self._last_keypad_poll: Optional[datetime] = None

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    # ------------------------------------------------------------------
    # Safe wrappers — each returns [] on failure so one broken endpoint
    # never takes down the entire poll cycle.
    # ------------------------------------------------------------------

    async def _safe_fetch(
        self, coro, label: str, critical: bool = False
    ) -> List[Dict[str, Any]]:
        """Execute *coro* and return its result, or [] on error.

        If *critical* is True the exception propagates (used for /devices).
        """
        try:
            return await coro
        except Exception as err:  # noqa: BLE001
            if critical:
                raise
            LOGGER.debug(
                "Could not fetch %s (may not be configured): %s", label, err
            )
            return []

    # ------------------------------------------------------------------
    # Merge helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_dedicated_list(
        devices: Dict[int, Dict[str, Any]],
        items: List[Dict[str, Any]],
        device_type: str,
    ) -> None:
        """Merge items from a dedicated endpoint into the master devices dict.

        On Crestron Home OS 4 the generic /devices endpoint returns only
        identity stubs for some device categories (or omits them entirely).
        Dedicated endpoints (/lights, /thermostats, /shades, /sensors) carry
        the full operational state.  For each item we either enrich an
        existing stub or insert a brand-new entry, and we always stamp the
        canonical ``type`` so entity platforms can filter reliably.
        """
        for item in items:
            item_id = item.get("id")
            if item_id is None:
                continue
            if item_id in devices:
                # Merge — dedicated data wins over the stub
                devices[item_id].update(item)
            else:
                devices[item_id] = dict(item)
            # Guarantee the type tag is set
            devices[item_id].setdefault("type", device_type)

    # ------------------------------------------------------------------
    # Keypad bridge polling
    # ------------------------------------------------------------------

    async def _poll_keypad_bridge(self) -> List[Dict[str, Any]]:
        """Poll the Keypad Event Bridge HTTP server for new events.

        Returns a list of new keypad event dicts since the last poll.
        Events are fired as HA events immediately.
        """
        if not self._keypad_bridge_url:
            return []

        try:
            now = datetime.now(timezone.utc)
            if self._last_keypad_poll is not None:
                since = self._last_keypad_poll.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                url = f"{self._keypad_bridge_url}/recent?since={since}"
            else:
                # First poll — just get the last few to avoid replaying history
                url = f"{self._keypad_bridge_url}/recent?count=0"

            session = self.hass.helpers.aiohttp_client.async_get_clientsession(
                self.hass, verify_ssl=False
            )

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    LOGGER.debug(
                        "Keypad bridge returned HTTP %s", resp.status
                    )
                    return []
                data = await resp.json()

            events = data.get("events", [])
            self._last_keypad_poll = now

            # Fire each new event as a Home Assistant event
            for event in events:
                event_data = {
                    "channel": event.get("channel"),
                    "channel_name": event.get("channelName", ""),
                    "action": event.get("action", ""),
                    "timestamp": event.get("timestamp", ""),
                }
                self.hass.bus.async_fire(EVENT_CRESTRON_KEYPAD, event_data)
                LOGGER.debug(
                    "Fired %s: channel=%s action=%s",
                    EVENT_CRESTRON_KEYPAD,
                    event_data["channel"],
                    event_data["action"],
                )

            return events

        except asyncio.TimeoutError:
            LOGGER.debug("Keypad bridge poll timed out")
            return []
        except Exception as err:  # noqa: BLE001
            LOGGER.debug("Keypad bridge poll error: %s", err)
            return []

    # ------------------------------------------------------------------
    # Main polling loop
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from ALL Crestron Home CWS REST API endpoints."""
        try:
            # Load room mapping once
            if not self.rooms:
                rooms_list = await self.api.get_rooms()
                self.rooms = {room["id"]: room["name"] for room in rooms_list}
                LOGGER.debug("Loaded room definitions: %s", self.rooms)

            LOGGER.debug("Polling Crestron Home processor state")

            # Fire every endpoint in parallel
            (
                devices_list,
                lights_list,
                shades_list,
                thermostats_list,
                sensors_list,
                scenes_list,
                doorlocks_list,
            ) = await asyncio.gather(
                self._safe_fetch(self.api.get_devices(), "devices", critical=True),
                self._safe_fetch(self.api.get_lights(), "lights"),
                self._safe_fetch(self.api.get_shades(), "shades"),
                self._safe_fetch(self.api.get_thermostats(), "thermostats"),
                self._safe_fetch(self.api.get_sensors(), "sensors"),
                self._safe_fetch(self.api.get_scenes(), "scenes"),
                self._safe_fetch(self.api.get_doorlocks(), "doorlocks"),
            )

            # Build the master devices dict from the generic endpoint first
            devices_dict: Dict[int, Dict[str, Any]] = {
                d["id"]: d for d in devices_list if "id" in d
            }

            # Layer dedicated endpoint data on top
            self._merge_dedicated_list(devices_dict, lights_list, "light")
            self._merge_dedicated_list(devices_dict, shades_list, "shade")
            self._merge_dedicated_list(devices_dict, thermostats_list, "thermostat")
            self._merge_dedicated_list(devices_dict, sensors_list, "sensor")

            # Scenes and door-locks stay in their own top-level dicts
            scenes_dict = {s["id"]: s for s in scenes_list if "id" in s}
            doorlocks_dict = {lk["id"]: lk for lk in doorlocks_list if "id" in lk}

            # Poll keypad bridge (fires events as side-effect)
            keypad_events = await self._poll_keypad_bridge()

            LOGGER.debug(
                "Poll complete — %d devices, %d scenes, %d locks, %d keypad events",
                len(devices_dict),
                len(scenes_dict),
                len(doorlocks_dict),
                len(keypad_events),
            )

            return {
                "devices": devices_dict,
                "scenes": scenes_dict,
                "doorlocks": doorlocks_dict,
                "keypad_events": keypad_events,
            }

        except CrestronHomeAPIError as err:
            raise UpdateFailed(
                f"Error communicating with Crestron API: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error updating Crestron Home data: {err}"
            ) from err
