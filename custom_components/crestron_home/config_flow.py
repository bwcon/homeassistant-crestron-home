"""Config flow for Crestron Home integration."""
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import CONF_PROTOCOL, CONF_SSL_VERIFY, DEFAULT_PORT, DEFAULT_PROTOCOL, DOMAIN
from .api import CrestronHomeAPI, CrestronHomeAuthError, CrestronHomeConnectionError

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(["https", "http"]),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_TOKEN): cv.string,
        vol.Required(CONF_SSL_VERIFY, default=False): cv.boolean,
    }
)


class CrestronHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crestron Home."""

    VERSION = 1

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
