"""Regression tests for the config flow contract.

The first version of this integration crashed with ``KeyError: 'today'`` in
production because config_flow expected a dict shape that
``api.async_get_prices`` no longer returned after a refactor. These tests pin
the contract between the two modules so that cannot happen again, and use the
real Home Assistant test harness so the flow runs exactly as it does live.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.elprisapi import api
from custom_components.elprisapi.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: F401


async def _fake_prices(zone, operator, day=None):
    return {
        "zone": zone,
        "unit": "dkk_per_kwh",
        "date": "2026-11-12",
        "prices": [{"hour": "2026-11-12T00:00:00+01:00", "total": 1.85}],
    }


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    """The flow must consume exactly the shape the API client returns."""
    with patch.object(
        api.ElprisApiClient, "async_get_prices", side_effect=_fake_prices
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"api_key": "key", "zone": "dk1", "operator": "trefor-el-net"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "api_key": "key",
        "zone": "dk1",
        "operator": "trefor-el-net",
    }
    assert "DK1" in result["title"]


async def test_config_flow_without_operator(hass: HomeAssistant) -> None:
    """The operator field is optional and normalises to None."""
    with patch.object(
        api.ElprisApiClient, "async_get_prices", side_effect=_fake_prices
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "key", "zone": "dk2", "operator": ""}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["operator"] is None


async def test_config_flow_empty_prices_is_no_data(hass: HomeAssistant) -> None:
    """An empty prices list must show no_data rather than crashing."""

    async def _empty(zone, operator, day=None):
        return {"zone": zone, "prices": []}

    with patch.object(api.ElprisApiClient, "async_get_prices", side_effect=_empty):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "key", "zone": "dk1", "operator": "bad"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_data"}


async def test_config_flow_unknown_operator_maps_to_no_data(
    hass: HomeAssistant,
) -> None:
    """A 404 for an unknown slug maps to no_data, not unknown."""
    with patch.object(
        api.ElprisApiClient,
        "async_get_prices",
        side_effect=api.ElprisApiError("HTTP 404 Unknown operator"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "key", "zone": "dk1", "operator": "nope"}
        )

    assert result["errors"] == {"base": "no_data"}


async def test_config_flow_auth_error(hass: HomeAssistant) -> None:
    """A rejected key must show invalid_auth."""
    with patch.object(
        api.ElprisApiClient,
        "async_get_prices",
        side_effect=api.ElprisApiAuthError("401"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "bad", "zone": "dk1"}
        )

    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_connection_error(hass: HomeAssistant) -> None:
    """An unreachable API must show cannot_connect."""
    with patch.object(
        api.ElprisApiClient,
        "async_get_prices",
        side_effect=api.ElprisApiConnectionError("timeout"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "key", "zone": "dk1"}
        )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_zone_and_operator_aborts(hass: HomeAssistant) -> None:
    """Configuring the same zone/operator twice must abort."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="dk1_trefor-el-net",
        data={"api_key": "key", "zone": "dk1", "operator": "trefor-el-net"},
    )
    existing.add_to_hass(hass)

    with patch.object(
        api.ElprisApiClient, "async_get_prices", side_effect=_fake_prices
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"api_key": "key2", "zone": "dk1", "operator": "trefor-el-net"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
