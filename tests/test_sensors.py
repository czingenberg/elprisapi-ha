"""Tests that the sensors actually return numbers.

An earlier version created every entity correctly but left all the component
sensors at ``unknown``, because the value callbacks read price components off
the slot dict instead of the slot's ``breakdown``. Entity existence tests did
not catch it, so these tests assert real values.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elprisapi import api
from custom_components.elprisapi.const import DOMAIN

CPH = ZoneInfo("Europe/Copenhagen")

COMPONENT_ENTITIES = [
    "sensor.elpris_api_dk1_current_price",
    "sensor.elpris_api_dk1_current_price_excl_vat",
    "sensor.elpris_api_dk1_spot_price",
    "sensor.elpris_api_dk1_electricity_tax",
    "sensor.elpris_api_dk1_system_tariff",
    "sensor.elpris_api_dk1_transmission_tariff",
    "sensor.elpris_api_dk1_grid_tariff",
    "sensor.elpris_api_dk1_vat",
]


def _payload(day: date) -> dict:
    return {
        "zone": "dk1",
        "unit": "dkk_per_kwh",
        "date": day.isoformat(),
        "prices": [
            {
                "hour": f"{day.isoformat()}T{h:02d}:00:00+01:00",
                "spot_price": 1.2322,
                "electricity_tax": 0.008,
                "system_tariff": 0.072,
                "transmission_tariff": 0.043,
                "grid_tariff": 0.1288,
                "total_excl_vat": 1.484,
                "vat": 0.371,
                "total": 1.855,
            }
            for h in range(24)
        ],
    }


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="dk1_trefor-el-net",
        data={"api_key": "key", "zone": "dk1", "operator": "trefor-el-net"},
    )


async def test_sensors_return_real_values(hass: HomeAssistant, entry) -> None:
    """Every component sensor must have a numeric state, not unknown."""
    entry.add_to_hass(hass)
    today = datetime.now(CPH).date()

    async def _fake(self, zone, operator, day=None):
        return _payload(day or today)

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    expected = {
        "sensor.elpris_api_dk1_current_price": 1.855,
        "sensor.elpris_api_dk1_current_price_excl_vat": 1.484,
        "sensor.elpris_api_dk1_spot_price": 1.2322,
        "sensor.elpris_api_dk1_electricity_tax": 0.008,
        "sensor.elpris_api_dk1_system_tariff": 0.072,
        "sensor.elpris_api_dk1_transmission_tariff": 0.043,
        "sensor.elpris_api_dk1_grid_tariff": 0.1288,
        "sensor.elpris_api_dk1_vat": 0.371,
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} missing"
        assert state.state != "unknown", f"{entity_id} is unknown"
        assert float(state.state) == pytest.approx(value), entity_id


async def test_daily_stats_sensors(hass: HomeAssistant, entry) -> None:
    """Today/tomorrow statistics must populate from the hourly data."""
    entry.add_to_hass(hass)
    today = datetime.now(CPH).date()

    async def _fake(self, zone, operator, day=None):
        return _payload(day or today)

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # All 24 hours are identical, so min == mean == max.
    for suffix in ("min", "mean", "max"):
        state = hass.states.get(f"sensor.elpris_api_dk1_today_{suffix}_price")
        assert state is not None
        assert float(state.state) == pytest.approx(1.855)


async def test_forecast_attribute_on_current_price(hass: HomeAssistant, entry) -> None:
    """sensor.current_price must carry the hourly forecast."""
    entry.add_to_hass(hass)
    today = datetime.now(CPH).date()

    async def _fake(self, zone, operator, day=None):
        return _payload(day or today)

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.elpris_api_dk1_current_price")
    prices = state.attributes["prices"]
    # The mock returns 24 hours for today and 24 for tomorrow.
    assert len(prices) == 48
    assert prices[0]["price"] == pytest.approx(1.855)
    assert set(prices[0]) == {"price", "start", "end"}
    # Both days are present and ordered.
    starts = [p["start"] for p in prices]
    assert starts == sorted(starts)


async def test_tomorrow_binary_sensor_off_without_data(
    hass: HomeAssistant, entry
) -> None:
    """The binary sensor is off until tomorrow's prices arrive."""
    entry.add_to_hass(hass)
    today = datetime.now(CPH).date()

    async def _fake(self, zone, operator, day=None):
        if day is None:
            return _payload(today)
        return {"zone": zone, "prices": []}

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.elpris_api_dk1_tomorrow_prices_available")
    assert state is not None
    assert state.state == "off"

    # Today's sensors still work.
    assert hass.states.get("sensor.elpris_api_dk1_current_price").state != "unknown"
