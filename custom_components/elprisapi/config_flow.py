"""Config flow for the Elpris API integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
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

# Dropdown value meaning "prices without a grid tariff". Also the operator
# part of the unique id for such entries.
NO_OPERATOR = "none"

_API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): _API_KEY_SELECTOR,
        vol.Required(CONF_ZONE, default=DEFAULT_ZONE): SelectSelector(
            SelectSelectorConfig(options=ZONES, mode=SelectSelectorMode.DROPDOWN)
        ),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): _API_KEY_SELECTOR})


async def _async_call(request: Awaitable[Any], on_api_error: str) -> tuple[Any, str | None]:
    """Run an API request and map its failure to a form error key."""
    try:
        return await request, None
    except ElprisApiAuthError:
        return None, "invalid_auth"
    except ElprisApiConnectionError:
        return None, "cannot_connect"
    except ElprisApiError:
        return None, on_api_error
    except Exception:  # noqa: BLE001 - surfaced to the user as a form error
        _LOGGER.exception("Unexpected error talking to Elpris API")
        return None, "unknown"


class ElprisApiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup for Elpris API."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow state carried between steps."""
        self._api_key = ""
        self._zone = DEFAULT_ZONE
        self._operators: list[SelectOptionDict] = []

    def _client(self, api_key: str) -> ElprisApiClient:
        return ElprisApiClient(
            session=async_get_clientsession(self.hass), api_key=api_key
        )

    async def _async_check_key(self, api_key: str) -> tuple[Any, str | None]:
        """Validate a key by listing the grid operators with it."""
        return await _async_call(
            self._client(api_key).async_get_operators(), "cannot_connect"
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the API key and price zone."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            payload, error = await self._async_check_key(api_key)
            if error is None:
                self._api_key = api_key
                self._zone = user_input[CONF_ZONE]
                self._operators = _operator_options(payload)
                return await self.async_step_operator()
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_operator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the grid operator from the API's own list."""
        errors: dict[str, str] = {}
        zone = self._zone

        if user_input is not None:
            choice = user_input[CONF_OPERATOR]
            operator = None if choice == NO_OPERATOR else choice

            await self.async_set_unique_id(f"{zone}_{operator or NO_OPERATOR}")
            self._abort_if_unique_id_configured()

            prices, error = await _async_call(
                self._client(self._api_key).async_get_prices(zone, operator),
                "no_data",
            )
            if error is None and not (prices or {}).get("prices"):
                error = "no_data"
            if error is None:
                return self.async_create_entry(
                    title=f"Elpris API ({zone.upper()}"
                    + (f" · {operator})" if operator else ")"),
                    data={
                        CONF_API_KEY: self._api_key,
                        CONF_ZONE: zone,
                        CONF_OPERATOR: operator,
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_OPERATOR, default=NO_OPERATOR): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=NO_OPERATOR, label="No grid operator"
                            ),
                            *self._operators,
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="operator",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the API rejected the stored key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a replacement API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            _, error = await self._async_check_key(api_key)
            if error is None:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_REAUTH_SCHEMA, errors=errors
        )


def _operator_options(payload: Any) -> list[SelectOptionDict]:
    """Dropdown options from the ``/operators`` response, sorted by name."""
    operators = payload.get("operators") if isinstance(payload, dict) else None
    options = [
        SelectOptionDict(value=op["slug"], label=str(op.get("name") or op["slug"]))
        for op in operators or []
        if isinstance(op, dict)
        and isinstance(op.get("slug"), str)
        and op["slug"] != NO_OPERATOR
    ]
    return sorted(options, key=lambda option: option["label"].casefold())
