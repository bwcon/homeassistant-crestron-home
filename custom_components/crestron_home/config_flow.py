"""Config flow for Crestron Home integration."""
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_KEYPAD_BRIDGE_HOST,
    CONF_KEYPAD_BRIDGE_PORT,
    CONF_POLL_DOORLOCKS,
    CONF_POLL_LIGHTS,
    CONF_POLL_SCENES,
    CONF_POLL_SENSORS,
    CONF_POLL_SHADES,
    CONF_POLL_THERMOSTATS,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    CONF_SSL_VERIFY,
    DEFAULT_KEYPAD_BRIDGE_PORT,
    DEFAULT_PORT,
    DEFAULT_PROTOCOL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .api import CrestronHomeAPI, CrestronHomeAuthError, CrestronHomeConnectionError

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(["https", "http"]),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_TOKEN): cv.string,
        vol.Required(CONF_SSL_VERIFY, default=False): cv.boolean,
        vol.Optional(CONF_KEYPAD_BRIDGE_HOST, default=""): cv.string,
        vol.Optional(CONF_KEYPAD_BRIDGE_PORT, default=DEFAULT_KEYPAD_BRIDGE_PORT): cv.port,
    }
)


class CrestronHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crestron Home."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return CrestronHomeOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            protocol = user_input[CONF_PROTOCOL]
            port = user_input[CONF_PORT]
            token = user_input[CONF_TOKEN]
            ssl_verify = user_input[CONF_SSL_VERIFY]

            # Unique ID based on host IP/Name
            await self.async_set_unique_id(f"{protocol}://{host}:{port}")
            self._abort_if_unique_id_configured()

            try:
                # Validate connection & credentials
                api = CrestronHomeAPI(
                    host=host,
                    port=port,
                    protocol=protocol,
                    token=token,
                    ssl_verify=ssl_verify,
                )
                await api.authenticate()
                await api.close()

                return self.async_create_entry(
                    title=f"Crestron Home ({host})",
                    data=user_input,
                )
            except CrestronHomeAuthError:
                errors["base"] = "invalid_auth"
            except CrestronHomeConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CrestronHomeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Crestron Home integration.

    Allows runtime configuration of:
    - Poll interval (15-300 seconds)
    - Which CWS endpoints to poll (lights, shades, thermostats, sensors, scenes, locks)
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Read current options (with defaults for first-time access)
        options = self._config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                    vol.Required(
                        CONF_POLL_LIGHTS,
                        default=options.get(CONF_POLL_LIGHTS, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_POLL_SHADES,
                        default=options.get(CONF_POLL_SHADES, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_POLL_THERMOSTATS,
                        default=options.get(CONF_POLL_THERMOSTATS, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_POLL_SENSORS,
                        default=options.get(CONF_POLL_SENSORS, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_POLL_SCENES,
                        default=options.get(CONF_POLL_SCENES, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_POLL_DOORLOCKS,
                        default=options.get(CONF_POLL_DOORLOCKS, True),
                    ): cv.boolean,
                }
            ),
        )
