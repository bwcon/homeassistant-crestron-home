"""DataUpdateCoordinator for Crestron Home."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_POLL_DOORLOCKS,
    CONF_POLL_LIGHTS,
    CONF_POLL_SCENES,
    CONF_POLL_SENSORS,
    CONF_POLL_SHADES,
    CONF_POLL_THERMOSTATS,
    CONF_SCAN_INTERVAL,
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
        entry: ConfigEntry,
        keypad_bridge_url: Optional[str] = None,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.rooms: Dict[int, str] = {}
        self.entry = entry
        self._keypad_bridge_url = keypad_bridge_url
        self._last_keypad_poll: Optional[datetime] = None

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    # ------------------------------------------------------------------
    # Options helpers
    # ------------------------------------------------------------------

    def _get_enabled_endpoints(self) -> Set[str]:
        """Return set of enabled endpoint names based on current options."""
        opts = self.entry.options
        enabled = set()
        if opts.get(CONF_POLL_LIGHTS, True):
            enabled.add("lights")
        if opts.get(CONF_POLL_SHADES, True):
            enabled.add("shades")
        if opts.get(CONF_POLL_THERMOSTATS, True):
            enabled.add("thermostats")
        if opts.get(CONF_POLL_SENSORS, True):
            enabled.add("sensors")
        if opts.get(CONF_POLL_SCENES, True):
            enabled.add("scenes")
        if opts.get(CONF_POLL_DOORLOCKS, True):
            enabled.add("doorlocks")
        return enabled

    def update_interval_from_options(self) -> None:
        """Re-read the scan interval from options (called on options update)."""
        scan_interval = self.entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        self.update_interval = timedelta(seconds=scan_interval)
        LOGGER.info("Poll interval updated to %d seconds", scan_interval)

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

            from homeassistant.helpers.aiohttp_client import async_get_clientsession

            session = async_get_clientsession(self.hass, verify_ssl=False)

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
        """Fetch data from enabled Crestron Home CWS REST API endpoints."""
        try:
            # Load room mapping once
            if not self.rooms:
                rooms_list = await self.api.get_rooms()
                self.rooms = {room["id"]: room["name"] for room in rooms_list}
                LOGGER.debug("Loaded room definitions: %s", self.rooms)

            enabled = self._get_enabled_endpoints()

            LOGGER.debug(
                "Polling Crestron Home processor (interval=%ss, endpoints=%s)",
                self.update_interval.total_seconds(),
                ",".join(sorted(enabled)) or "devices-only",
            )

            # Always fetch /devices (the master list)
            fetches = [
                self._safe_fetch(self.api.get_devices(), "devices", critical=True),
            ]
            # Conditionally add each dedicated endpoint
            fetch_labels = []
            if "lights" in enabled:
                fetches.append(self._safe_fetch(self.api.get_lights(), "lights"))
                fetch_labels.append("lights")
            if "shades" in enabled:
                fetches.append(self._safe_fetch(self.api.get_shades(), "shades"))
                fetch_labels.append("shades")
            if "thermostats" in enabled:
                fetches.append(
                    self._safe_fetch(self.api.get_thermostats(), "thermostats")
                )
                fetch_labels.append("thermostats")
            if "sensors" in enabled:
                fetches.append(self._safe_fetch(self.api.get_sensors(), "sensors"))
                fetch_labels.append("sensors")
            if "scenes" in enabled:
                fetches.append(self._safe_fetch(self.api.get_scenes(), "scenes"))
                fetch_labels.append("scenes")
            if "doorlocks" in enabled:
                fetches.append(
                    self._safe_fetch(self.api.get_doorlocks(), "doorlocks")
                )
                fetch_labels.append("doorlocks")

            # Fire all enabled endpoints in parallel
            results = await asyncio.gather(*fetches)

            # First result is always /devices
            devices_list = results[0]
            result_idx = 1

            # Build the master devices dict from the generic endpoint first
            devices_dict: Dict[int, Dict[str, Any]] = {
                d["id"]: d for d in devices_list if "id" in d
            }

            # Layer dedicated endpoint data on top
            lights_list: List[Dict[str, Any]] = []
            shades_list: List[Dict[str, Any]] = []
            thermostats_list: List[Dict[str, Any]] = []
            sensors_list: List[Dict[str, Any]] = []
            scenes_dict: Dict[int, Dict[str, Any]] = {}
            doorlocks_dict: Dict[int, Dict[str, Any]] = {}

            for label in fetch_labels:
                data = results[result_idx]
                result_idx += 1

                if label == "lights":
                    lights_list = data
                    self._merge_dedicated_list(devices_dict, data, "light")
                elif label == "shades":
                    shades_list = data
                    self._merge_dedicated_list(devices_dict, data, "shade")
                elif label == "thermostats":
                    thermostats_list = data
                    self._merge_dedicated_list(devices_dict, data, "thermostat")
                elif label == "sensors":
                    sensors_list = data
                    self._merge_dedicated_list(devices_dict, data, "sensor")
                elif label == "scenes":
                    scenes_dict = {s["id"]: s for s in data if "id" in s}
                elif label == "doorlocks":
                    doorlocks_dict = {lk["id"]: lk for lk in data if "id" in lk}

            # Poll keypad bridge (fires events as side-effect)
            keypad_events = await self._poll_keypad_bridge()

            endpoint_count = 1 + len(fetch_labels)  # 1 for /devices
            LOGGER.debug(
                "Poll complete — %d endpoints, %d devices, %d scenes, "
                "%d locks, %d keypad events",
                endpoint_count,
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
