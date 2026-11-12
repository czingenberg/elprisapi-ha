"""Tests for the coordinator's data assembly, caching and failure handling."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.elprisapi import api
from custom_components.elprisapi.const import SCAN_INTERVAL_IDLE, SCAN_INTERVAL_WAITING
from custom_components.elprisapi.coordinator import ElprisApiCoordinator
from custom_components.elprisapi.pricing import forecast_attribute

from helpers import fake_prices, mock_entry

CPH = ZoneInfo("Europe/Copenhagen")
D12 = date(2026, 11, 12)
D13 = date(2026, 11, 13)
HOURLY = [float(h) for h in range(24)]  # total == hour of day


def _coordinator(hass: HomeAssistant) -> ElprisApiCoordinator:
    entry = mock_entry()
    entry.add_to_hass(hass)
    return ElprisApiCoordinator(hass, entry)


def _patch_prices(fake):
    return patch.object(api.ElprisApiClient, "async_get_prices", fake)


async def test_coordinator_combines_today_and_tomorrow(hass: HomeAssistant) -> None:
    """Both days come from one range request, and stats cover each day."""
    today = datetime.now(CPH).date()
    tomorrow = today + timedelta(days=1)
    calls: list[dict] = []

    with _patch_prices(
        fake_prices({today: [1.0, 2.0, 3.0], tomorrow: [4.0, 5.0]}, calls)
    ):
        data = await _coordinator(hass)._async_update_data()

    assert calls == [{"day": None, "start": today, "end": tomorrow}]
    assert len(data.slots) == 5
    assert data.tomorrow_available is True
    assert data.today_stats == {"min": 1.0, "mean": 2.0, "max": 3.0}
    assert data.tomorrow_stats == {"min": 4.0, "mean": 4.5, "max": 5.0}
    assert [f["price"] for f in forecast_attribute(data.slots)] == [1, 2, 3, 4, 5]


async def test_tomorrow_not_published_yet(hass: HomeAssistant) -> None:
    """Missing tomorrow prices must not break today's sensors."""
    today = datetime.now(CPH).date()

    with _patch_prices(fake_prices({today: [1.0, 2.0]})):
        data = await _coordinator(hass)._async_update_data()

    assert len(data.slots) == 2
    assert data.tomorrow_available is False
    assert data.tomorrow_stats is None
    assert data.today_stats is not None


async def test_falls_back_to_today_when_range_is_rejected(hass: HomeAssistant) -> None:
    """An HTTP error on the range request retries with the plain today request."""
    today = datetime.now(CPH).date()
    serve_today = fake_prices({today: [1.0, 2.0]})

    async def _fake(self, zone, operator, day=None, *, start=None, end=None):
        if start is not None:
            raise api.ElprisApiError("HTTP 400 range not available")
        return await serve_today(self, zone, operator, day)

    with _patch_prices(_fake):
        data = await _coordinator(hass)._async_update_data()

    assert len(data.today_slots) == 2


async def test_coordinator_raises_on_empty(hass: HomeAssistant) -> None:
    """No prices at all is a genuine failure and must raise UpdateFailed."""
    with _patch_prices(fake_prices({})), pytest.raises(UpdateFailed):
        await _coordinator(hass)._async_update_data()


async def test_auth_failure_triggers_reauth(hass: HomeAssistant) -> None:
    """A rejected key must raise ConfigEntryAuthFailed so HA starts reauth."""
    with (
        patch.object(
            api.ElprisApiClient,
            "async_get_prices",
            side_effect=api.ElprisApiAuthError("401"),
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await _coordinator(hass)._async_update_data()


async def test_day_bucketing_uses_copenhagen_not_ha_timezone(
    hass: HomeAssistant,
) -> None:
    """The API's "today" is the Danish day, regardless of the HA instance timezone.

    The test harness runs HA in US/Pacific. Freezing at 06:00 UTC puts
    Copenhagen on the 13th while Pacific is still on the 12th, so a coordinator
    that bucketed by the HA timezone would put the stats on the wrong day.
    """
    from homeassistant.util import dt as dt_util

    with freeze_time("2026-11-13 06:00:00+00:00"):
        assert dt_util.now().date() == D12

        with _patch_prices(fake_prices({D13: HOURLY})):
            data = await _coordinator(hass)._async_update_data()

    assert len(data.today_slots) == 24
    assert data.current_breakdown["total"] == 7.0  # 06:00 UTC is 07:00 in Denmark


async def test_outage_is_served_from_cache_while_it_covers_now(
    hass: HomeAssistant,
) -> None:
    """A failed poll keeps the sensors alive until the cached prices run out."""
    coordinator = _coordinator(hass)
    down = patch.object(
        api.ElprisApiClient,
        "async_get_prices",
        side_effect=api.ElprisApiConnectionError("timeout"),
    )

    with freeze_time("2026-11-12 12:30:00+00:00") as clock:
        with _patch_prices(fake_prices({D12: HOURLY})):
            await coordinator._async_update_data()

        with down:
            clock.move_to("2026-11-12 14:30:00+00:00")
            data = await coordinator._async_update_data()
            # Served from cache, and following the clock: 15:30 Danish time.
            assert data.current_breakdown["total"] == 15.0
            assert coordinator.update_interval == SCAN_INTERVAL_WAITING

            # Past the end of the cached day there is nothing left to serve.
            clock.move_to("2026-11-13 00:30:00+00:00")
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()


async def test_tomorrow_is_kept_if_a_later_response_omits_it(
    hass: HomeAssistant,
) -> None:
    """Published prices must not vanish again, which would re-fire automations."""
    coordinator = _coordinator(hass)

    with freeze_time("2026-11-12 13:00:00+00:00"):
        with _patch_prices(fake_prices({D12: HOURLY, D13: HOURLY})):
            await coordinator._async_update_data()
        with _patch_prices(fake_prices({D12: HOURLY})):
            data = await coordinator._async_update_data()

    assert data.tomorrow_available is True


async def test_clock_tick_follows_the_hour_and_the_day(hass: HomeAssistant) -> None:
    """Between polls, the current slot and today/tomorrow follow the clock."""
    coordinator = _coordinator(hass)
    tomorrow_totals = [100.0 + h for h in range(24)]

    with freeze_time("2026-11-12 12:59:00+00:00") as clock:  # 13:59 Danish time
        with _patch_prices(fake_prices({D12: HOURLY, D13: tomorrow_totals})):
            coordinator.data = await coordinator._async_update_data()
        assert coordinator.data.current_breakdown["total"] == 13.0

        clock.move_to("2026-11-12 13:00:00+00:00")
        coordinator.async_handle_clock_tick()
        assert coordinator.data.current_breakdown["total"] == 14.0
        assert coordinator.data.tomorrow_available is True

        clock.move_to("2026-11-12 23:00:00+00:00")  # Danish midnight
        coordinator.async_handle_clock_tick()

    data = coordinator.data
    assert data.current_breakdown["total"] == 100.0
    assert data.today_stats == {"min": 100.0, "mean": 111.5, "max": 123.0}
    assert data.tomorrow_available is False
    assert len(data.slots) == 24  # yesterday was pruned


@pytest.mark.parametrize(
    ("utc_now", "days", "expected"),
    [
        # 11:00 Danish time: tomorrow is not expected yet.
        ("2026-11-12 10:00:00+00:00", {D12: HOURLY}, SCAN_INTERVAL_IDLE),
        # 13:30 Danish time and still no tomorrow: poll often.
        ("2026-11-12 12:30:00+00:00", {D12: HOURLY}, SCAN_INTERVAL_WAITING),
        # Tomorrow has arrived: nothing more to wait for today.
        ("2026-11-12 12:30:00+00:00", {D12: HOURLY, D13: HOURLY}, SCAN_INTERVAL_IDLE),
    ],
)
async def test_polls_often_only_while_waiting_for_tomorrow(
    hass: HomeAssistant, utc_now, days, expected
) -> None:
    coordinator = _coordinator(hass)
    with freeze_time(utc_now), _patch_prices(fake_prices(days)):
        await coordinator._async_update_data()
    assert coordinator.update_interval == expected
