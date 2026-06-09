"""Python client wrapper for Crestron Home REST API."""
import asyncio
import time
from typing import Any, Dict, List, Optional
import aiohttp

from .const import LOGGER

class CrestronHomeAPIError(Exception):
    """Base exception for Crestron Home API errors."""

class CrestronHomeAuthError(CrestronHomeAPIError):
    """Authentication or authorization exception."""

class CrestronHomeConnectionError(CrestronHomeAPIError):
    """Connection error when communicating with processor."""


class CrestronHomeAPI:
    """API Client for Crestron Home CWS REST interface."""

    def __init__(
        self,
        host: str,
        port: int,
        protocol: str,
        token: str,
        ssl_verify: bool = False,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._protocol = protocol
        self._token = token
        self._ssl_verify = ssl_verify
        self._session = session or aiohttp.ClientSession()
        self._own_session = session is None

        self._auth_key: Optional[str] = None
        self._session_start: Optional[float] = None
        # Base url: e.g., https://192.168.1.100:443/cws/api
        self._base_url = f"{self._protocol}://{self._host}:{self._port}/cws/api"

    @property
    def host(self) -> str:
        """Return host."""
        return self._host

    def _is_session_valid(self) -> bool:
        """Check if cached auth session key is still valid (9 minutes lifetime)."""
        if not self._auth_key or not self._session_start:
            return False
        # 540 seconds = 9 minutes (Crestron session times out in 10 minutes)
        return (time.time() - self._session_start) < 540

    async def authenticate(self) -> str:
        """Authenticate with the processor and get an AuthKey."""
        url = f"{self._base_url}/login"
        headers = {"Crestron-RestAPI-AuthToken": self._token}
        ssl_ctx = False if not self._ssl_verify else None

        LOGGER.debug("Authenticating with Crestron Home at %s", url)
        try:
            async with self._session.get(url, headers=headers, ssl=ssl_ctx) as response:
                if response.status == 401:
                    raise CrestronHomeAuthError("Invalid Web API token provided")
                response.raise_for_status()
                data = await response.json()
                
                # Crestron Home API can return lowercase authkey or camelcase AuthKey
                auth_key = data.get("AuthKey") or data.get("authkey")
                if not auth_key:
                    raise CrestronHomeAuthError("AuthKey not returned by processor during login")
                
                self._auth_key = auth_key
                self._session_start = time.time()
                LOGGER.debug("Crestron Home session successfully established")
                return auth_key
        except aiohttp.ClientResponseError as err:
            raise CrestronHomeAPIError(f"HTTP error during authentication: {err.status}") from err
        except aiohttp.ClientConnectorError as err:
            raise CrestronHomeConnectionError(f"Failed to connect to processor: {err}") from err
        except Exception as err:
            raise CrestronHomeAPIError(f"Unexpected error during authentication: {err}") from err

    async def request(
        self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to the processor."""
        if not self._is_session_valid():
            await self.authenticate()

        url = f"{self._base_url}{endpoint}"
        headers = {
            "Crestron-RestAPI-AuthKey": self._auth_key,
        }
        ssl_ctx = False if not self._ssl_verify else None

        LOGGER.debug("Sending %s request to %s", method, url)
        try:
            if method == "GET":
                async with self._session.get(url, headers=headers, ssl=ssl_ctx) as response:
                    if response.status == 401:
                        # Session might have expired on processor side, try once more
                        LOGGER.info("Session unauthorized (401), re-authenticating and retrying")
                        await self.authenticate()
                        headers["Crestron-RestAPI-AuthKey"] = self._auth_key
                        async with self._session.get(url, headers=headers, ssl=ssl_ctx) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                    response.raise_for_status()
                    return await response.json()

            if method == "POST":
                headers["Content-Type"] = "application/json"
                async with self._session.post(url, headers=headers, json=json_data, ssl=ssl_ctx) as response:
                    if response.status == 401:
                        LOGGER.info("Session unauthorized (401), re-authenticating and retrying")
                        await self.authenticate()
                        headers["Crestron-RestAPI-AuthKey"] = self._auth_key
                        async with self._session.post(url, headers=headers, json=json_data, ssl=ssl_ctx) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                    response.raise_for_status()
                    return await response.json()

            raise ValueError(f"Unsupported HTTP method: {method}")

        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                raise CrestronHomeAuthError("Unauthorized access to Crestron processor") from err
            raise CrestronHomeAPIError(f"HTTP error: {err.status} for {endpoint}") from err
        except aiohttp.ClientConnectorError as err:
            raise CrestronHomeConnectionError(f"Connection error to processor: {err}") from err
        except Exception as err:
            raise CrestronHomeAPIError(f"Error communicating with Crestron processor: {err}") from err

    async def get_rooms(self) -> List[Dict[str, Any]]:
        """Retrieve all configured rooms."""
        data = await self.request("GET", "/rooms")
        return data.get("rooms", [])

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Retrieve all devices."""
        data = await self.request("GET", "/devices")
        return data.get("devices", [])

    async def get_lights(self) -> List[Dict[str, Any]]:
        """Retrieve all lights (also filterable via /devices)."""
        data = await self.request("GET", "/lights")
        return data.get("lights", [])

    async def get_shades(self) -> List[Dict[str, Any]]:
        """Retrieve all shades."""
        data = await self.request("GET", "/shades")
        return data.get("shades", [])

    async def get_thermostats(self) -> List[Dict[str, Any]]:
        """Retrieve all thermostats."""
        data = await self.request("GET", "/thermostats")
        return data.get("thermostats", [])

    async def get_scenes(self) -> List[Dict[str, Any]]:
        """Retrieve all scenes."""
        data = await self.request("GET", "/scenes")
        return data.get("scenes", [])

    async def get_sensors(self) -> List[Dict[str, Any]]:
        """Retrieve all sensors."""
        data = await self.request("GET", "/sensors")
        return data.get("sensors", [])

    async def get_doorlocks(self) -> List[Dict[str, Any]]:
        """Retrieve all doorlocks."""
        data = await self.request("GET", "/doorlocks")
        return data.get("doorlocks", [])

    async def set_light_state(self, light_id: int, level: int, fade_time: int = 0) -> bool:
        """Set state of a light. level range is 0 (off) to 65535 (max brightness)."""
        payload = {
            "lights": [
                {
                    "id": light_id,
                    "level": level,
                    "time": fade_time
                }
            ]
        }
        res = await self.request("POST", "/lights/SetState", json_data=payload)
        return res.get("status") == "success"

    async def set_shade_position(self, shade_id: int, position: int) -> bool:
        """Set position of a shade. position range is 0 (closed) to 65535 (open)."""
        payload = {
            "shades": [
                {
                    "id": shade_id,
                    "position": position
                }
            ]
        }
        res = await self.request("POST", "/shades/SetState", json_data=payload)
        return res.get("status") == "success"

    async def recall_scene(self, scene_id: int) -> bool:
        """Recall/activate a scene by ID."""
        res = await self.request("POST", f"/scenes/recall/{scene_id}")
        return res.get("status") == "success"

    async def recall_quickaction(self, quickaction_id: int) -> bool:
        """Recall/activate a quick action by ID."""
        res = await self.request("POST", f"/quickactions/recall/{quickaction_id}")
        return res.get("status") == "success"

    async def set_thermostat_setpoint(
        self, thermostat_id: int, setpoints: List[Dict[str, Any]]
    ) -> bool:
        """
        Set setpoint for a thermostat.
        setpoints parameter structure: [{"type": "Cool", "temperature": 220}]
        """
        payload = {
            "id": thermostat_id,
            "setpoints": setpoints
        }
        res = await self.request("POST", "/thermostats/SetPoint", json_data=payload)
        return res.get("status") == "success"

    async def set_thermostat_mode(self, thermostat_id: int, mode: str) -> bool:
        """Set HVAC operating mode (HEAT/COOL/AUTO/OFF)."""
        payload = {
            "thermostats": [
                {
                    "id": thermostat_id,
                    "mode": mode
                }
            ]
        }
        res = await self.request("POST", "/thermostats/mode", json_data=payload)
        return res.get("status") == "success"

    async def set_thermostat_fan_mode(self, thermostat_id: int, fan_mode: str) -> bool:
        """Set fan operating mode (AUTO/ON)."""
        payload = {
            "thermostats": [
                {
                    "id": thermostat_id,
                    "mode": fan_mode
                }
            ]
        }
        res = await self.request("POST", "/thermostats/fanmode", json_data=payload)
        return res.get("status") == "success"

    async def lock_door(self, lock_id: int) -> bool:
        """Lock a door lock."""
        res = await self.request("POST", f"/doorlocks/lock/{lock_id}")
        return res.get("status") == "success"

    async def unlock_door(self, lock_id: int) -> bool:
        """Unlock a door lock."""
        res = await self.request("POST", f"/doorlocks/unlock/{lock_id}")
        return res.get("status") == "success"

    async def close(self) -> None:
        """Close ClientSession if owned."""
        if self._own_session and self._session:
            await self._session.close()
