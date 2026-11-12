"""Tests for the coordinator's data assembly and failure handling."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elprisapi import api
from custom_components.elprisapi.const import DOMAIN
from custom_components.elprisapi.coordinator import ElprisApiCoordinator


def _payload(day: date, totals: list[float]) -> dict:
    return {
        "zone": "dk1",
        "unit": "dkk_per_kwh",
        "date": day.isoformat(),
        "prices": [
            {
                "hour": f"{day.isoformat()}T{i:02d}:00:00+01:00",
                "spot_price": t - 0.5,
                "electricity_tax": 0.008,
                "system_tariff": 0.072,
                "transmission_tariff": 0.043,
                "grid_tariff": 0.1288,
                "total_excl_vat": t * 0.8,
                "vat": t * 0.2,
                "total": t,
            }
            for i, t in enumerate(totals)
        ],
    }


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="dk1_trefor-el-net",
        data={"api_key": "key", "zone": "dk1", "operator": "trefor-el-net"},
    )


async def test_coordinator_combines_today_and_tomorrow(hass: HomeAssistant) -> None:
    """Today + tomorrow slots are merged, and stats cover both days."""
    entry = _entry()
    entry.add_to_hass(hass)
    today = datetime.now(ZoneInfo("Europe/Copenhagen")).date()

    async def _fake(self, zone, operator, day=None):
        if day is None:
            return _payload(today, [1.0, 2.0, 3.0])
        return _payload(day, [4.0, 5.0])

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        coordinator = ElprisApiCoordinator(hass, entry)
        data = await coordinator._async_update_data()

    assert len(data.slots) == 5
    assert data.tomorrow_available is True
    assert data.today_stats == {"min": 1.0, "mean": 2.0, "max": 3.0}
    assert data.tomorrow_stats == {"min": 4.0, "mean": 4.5, "max": 5.0}


async def test_coordinator_survives_tomorrow_failure(hass: HomeAssistant) -> None:
    """Tomorrow being unavailable must not break today's sensors."""
    entry = _entry()
    entry.add_to_hass(hass)
    today = datetime.now(ZoneInfo("Europe/Copenhagen")).date()

    async def _fake(self, zone, operator, day=None):
        if day is None:
            return _payload(today, [1.0, 2.0])
        raise api.ElprisApiError("HTTP 500")

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        coordinator = ElprisApiCoordinator(hass, entry)
        data = await coordinator._async_update_data()

    assert len(data.slots) == 2
    assert data.tomorrow_available is False
    assert data.tomorrow_stats is None
    assert data.today_stats is not None


async def test_coordinator_raises_on_empty_today(hass: HomeAssistant) -> None:
    """No prices at all is a genuine failure and must raise UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    entry = _entry()
    entry.add_to_hass(hass)

    async def _fake(self, zone, operator, day=None):
        return {"zone": zone, "prices": []}

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        coordinator = ElprisApiCoordinator(hass, entry)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


async def test_coordinator_raises_on_auth_failure(hass: HomeAssistant) -> None:
    """A rejected key must surface as UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    entry = _entry()
    entry.add_to_hass(hass)

    with patch.object(
        api.ElprisApiClient,
        "async_get_prices",
        side_effect=api.ElprisApiAuthError("401"),
    ):
        coordinator = ElprisApiCoordinator(hass, entry)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


async def test_forecast_covers_both_days(hass: HomeAssistant) -> None:
    """Forecast attributes must include every slot we hold."""
    from custom_components.elprisapi.pricing import forecast_attribute

    entry = _entry()
    entry.add_to_hass(hass)
    today = datetime.now(ZoneInfo("Europe/Copenhagen")).date()

    async def _fake(self, zone, operator, day=None):
        if day is None:
            return _payload(today, [1.0, 2.0])
        return _payload(day, [3.0, 4.0])

    with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
        coordinator = ElprisApiCoordinator(hass, entry)
        data = await coordinator._async_update_data()

    forecast = forecast_attribute(data.slots)
    assert len(forecast) == 4
    assert [f["price"] for f in forecast] == [1.0, 2.0, 3.0, 4.0]


async def test_day_bucketing_uses_copenhagen_not_ha_timezone(
    hass: HomeAssistant,
) -> None:
    """The API's "today" is the Danish day, regardless of the HA instance timezone.

    The test harness runs HA in US/Pacific. Freezing at 06:00 UTC puts
    Copenhagen on the 13th while Pacific is still on the 12th, so a coordinator
    that bucketed by the HA timezone would put the stats on the wrong day.
    """
    from freezegun import freeze_time
    from homeassistant.util import dt as dt_util

    entry = _entry()
    entry.add_to_hass(hass)

    with freeze_time("2026-11-13 06:00:00+00:00"):
        danish_today = datetime.now(ZoneInfo("Europe/Copenhagen")).date()
        ha_today = dt_util.now().date()
        assert danish_today != ha_today, "timezones should disagree at this instant"
        assert danish_today.isoformat() == "2026-11-13"
        assert ha_today.isoformat() == "2026-11-12"

        async def _fake(self, zone, operator, day=None):
            if day is None:
                return _payload(danish_today, [1.0, 2.0])
            return {"zone": zone, "prices": []}

        with patch.object(api.ElprisApiClient, "async_get_prices", _fake):
            coordinator = ElprisApiCoordinator(hass, entry)
            data = await coordinator._async_update_data()

    # Stats landed on the Danish day, not the HA-local day.
    assert data.today_stats == {"min": 1.0, "mean": 1.5, "max": 2.0}
    assert len(data.today_slots) == 2
