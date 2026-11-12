"""Tests that the entities are set up correctly and return real numbers.

An earlier version created every entity correctly but left all the component
sensors at ``unknown``, because the value callbacks read price components off
the slot dict instead of the slot's ``breakdown``. Entity existence tests did
not catch it, so these tests assert real values.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.elprisapi import api

from helpers import FLAT_DAY, fake_prices, mock_entry

CPH = ZoneInfo("Europe/Copenhagen")
PREFIX = "sensor.elpris_api_dk1_trefor_el_net"
TOMORROW_SENSOR = "binary_sensor.elpris_api_dk1_trefor_el_net_tomorrow_prices_available"


async def _setup(hass: HomeAssistant, days: dict[date, list[float]], **entry_kwargs):
    entry = mock_entry(**entry_kwargs)
    entry.add_to_hass(hass)
    with patch.object(api.ElprisApiClient, "async_get_prices", fake_prices(days)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _both_days() -> dict[date, list[float]]:
    today = datetime.now(CPH).date()
    return {today: FLAT_DAY, today + timedelta(days=1): FLAT_DAY}


async def test_sensors_return_real_values(hass: HomeAssistant) -> None:
    """Every component sensor must have a numeric state, not unknown."""
    await _setup(hass, _both_days())

    expected = {
        f"{PREFIX}_current_price": 1.855,
        f"{PREFIX}_current_price_excl_vat": 1.484,
        f"{PREFIX}_spot_price": 1.2322,
        f"{PREFIX}_electricity_tax": 0.008,
        f"{PREFIX}_system_tariff": 0.072,
        f"{PREFIX}_transmission_tariff": 0.043,
        f"{PREFIX}_grid_tariff": 0.1288,
        f"{PREFIX}_vat": 0.371,
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} missing"
        assert float(state.state) == pytest.approx(value), entity_id


async def test_price_sensors_are_measurements_not_monetary_totals(
    hass: HomeAssistant,
) -> None:
    """A price per kWh is a measurement; "monetary total" corrupts statistics."""
    await _setup(hass, _both_days())

    state = hass.states.get(f"{PREFIX}_current_price")
    assert state.attributes["unit_of_measurement"] == "DKK/kWh"
    assert state.attributes["state_class"] == "measurement"
    assert "device_class" not in state.attributes

    daily = hass.states.get(f"{PREFIX}_today_mean_price")
    assert "state_class" not in daily.attributes
    assert "device_class" not in daily.attributes


async def test_daily_stats_sensors(hass: HomeAssistant) -> None:
    """Today/tomorrow statistics must populate from the hourly data."""
    await _setup(hass, _both_days())

    # All 24 hours are identical, so min == mean == max.
    for day in ("today", "tomorrow"):
        for suffix in ("min", "mean", "max"):
            state = hass.states.get(f"{PREFIX}_{day}_{suffix}_price")
            assert state is not None
            assert float(state.state) == pytest.approx(1.855)


async def test_forecast_attribute_on_current_price(hass: HomeAssistant) -> None:
    """The current price sensor must carry the forecast for both days."""
    await _setup(hass, _both_days())

    prices = hass.states.get(f"{PREFIX}_current_price").attributes["prices"]
    assert len(prices) == 48
    assert prices[0]["price"] == pytest.approx(1.855)
    assert set(prices[0]) == {"price", "start", "end"}
    starts = [p["start"] for p in prices]
    assert starts == sorted(starts)


async def test_tomorrow_binary_sensor(hass: HomeAssistant) -> None:
    """Off until tomorrow's prices arrive, and a plain on/off sensor."""
    today = datetime.now(CPH).date()
    await _setup(hass, {today: FLAT_DAY})

    state = hass.states.get(TOMORROW_SENSOR)
    assert state is not None
    assert state.state == "off"
    # No "connectivity" class, which would read Connected/Disconnected.
    assert "device_class" not in state.attributes

    # Today's sensors still work.
    assert hass.states.get(f"{PREFIX}_current_price").state != "unknown"


async def test_current_price_changes_on_the_hour_without_a_poll(
    hass: HomeAssistant,
) -> None:
    """The state must follow the clock, not wait for the next API poll."""
    day = date(2026, 11, 12)
    totals = [float(h) for h in range(24)]

    with freeze_time("2026-11-12 12:59:30+00:00") as clock:  # 13:59:30 Danish time
        await _setup(hass, {day: totals})
        assert float(hass.states.get(f"{PREFIX}_current_price").state) == 13.0

        # No API patch is active here: any poll would fail the update.
        clock.move_to("2026-11-12 13:00:00+00:00")
        async_fire_time_changed(
            hass, datetime(2026, 11, 12, 13, 0, 0, tzinfo=timezone.utc)
        )
        await hass.async_block_till_done()

        assert float(hass.states.get(f"{PREFIX}_current_price").state) == 14.0


async def test_operators_in_one_zone_get_distinct_devices(hass: HomeAssistant) -> None:
    """Two operators in the same zone must not share a device name."""
    days = _both_days()
    await _setup(hass, days, operator="trefor-el-net")
    await _setup(hass, days, operator="n1")
    await _setup(hass, days, operator=None)

    # Iterate the registry rather than using `.devices` as a mapping, which
    # Home Assistant deprecated in 2026.11 (breaking in 2027.9). Iteration is
    # the supported replacement.
    names = sorted(device.name for device in dr.async_get(hass).devices)
    assert names == [
        "Elpris API DK1",
        "Elpris API DK1 n1",
        "Elpris API DK1 trefor-el-net",
    ]
    assert hass.states.get("sensor.elpris_api_dk1_n1_current_price") is not None
    assert hass.states.get("sensor.elpris_api_dk1_current_price") is not None


async def test_unload(hass: HomeAssistant) -> None:
    """The entry unloads cleanly and its entities become unavailable."""
    entry = await _setup(hass, _both_days())

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(f"{PREFIX}_current_price").state == "unavailable"
