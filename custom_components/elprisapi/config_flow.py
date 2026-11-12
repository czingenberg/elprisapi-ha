"""Config flow for the Elpris API integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ElprisApiAuthError,
    ElprisApiClient,
    ElprisApiConnectionError,
    ElprisApiError,
)
from .const import (
    CONF_API_KEY,
    CONF_OPERATOR,
    CONF_ZONE,
    DEFAULT_ZONE,
    DOMAIN,
    ZONES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_ZONE, default=DEFAULT_ZONE): SelectSelector(
            SelectSelectorConfig(
                options=ZONES, mode=SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Optional(CONF_OPERATOR): TextSelector(),
    }
)


class ElprisApiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup for Elpris API."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the API key, price zone and optional grid operator."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            zone = user_input[CONF_ZONE]
            operator = (user_input.get(CONF_OPERATOR) or "").strip() or None

            await self.async_set_unique_id(f"{zone}_{operator or 'none'}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = ElprisApiClient(session=session, api_key=api_key)

            try:
                prices = await client.async_get_prices(zone, operator)
            except ElprisApiAuthError:
                errors["base"] = "invalid_auth"
            except ElprisApiConnectionError:
                errors["base"] = "cannot_connect"
            except ElprisApiError:
                # A 400/404 here almost always means an unknown operator slug.
                errors["base"] = "no_data"
            except Exception:  # noqa: BLE001 - surfaced to the user as a form error
                _LOGGER.exception("Unexpected error validating Elpris API credentials")
                errors["base"] = "unknown"
            else:
                if not prices.get("prices"):
                    # Credentials are fine but the zone/operator combination
                    # returned no data, which almost always means a bad slug.
                    errors["base"] = "no_data"
                else:
                    return self.async_create_entry(
                        title=f"Elpris API ({zone.upper()}"
                        + (f" · {operator})" if operator else ")"),
                        data={
                            CONF_API_KEY: api_key,
                            CONF_ZONE: zone,
                            CONF_OPERATOR: operator,
                        },
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
