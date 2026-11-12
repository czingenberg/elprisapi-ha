"""Shared builders for fake Elpris API responses."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elprisapi.const import DOMAIN

FLAT_DAY = [1.855] * 24


def price_entries(day: date, totals: list[float]) -> list[dict[str, Any]]:
    """Hourly entries for one winter-time day, one per value in ``totals``."""
    return [
        {
            "hour": f"{day.isoformat()}T{hour:02d}:00:00+01:00",
            "spot_price": 1.2322,
            "electricity_tax": 0.008,
            "system_tariff": 0.072,
            "transmission_tariff": 0.043,
            "grid_tariff": 0.1288,
            "total_excl_vat": 1.484,
            "vat": 0.371,
            "total": total,
        }
        for hour, total in enumerate(totals)
    ]


def fake_prices(days: dict[date, list[float]], calls: list[dict] | None = None):
    """Stand-in for ``ElprisApiClient.async_get_prices`` serving ``days``.

    Honours ``day`` and ``start``/``end`` the way the API does; with neither
    it serves the earliest known day, which the tests use as "today".
    """

    async def _fake(self, zone, operator, day=None, *, start=None, end=None):
        if calls is not None:
            calls.append({"day": day, "start": start, "end": end})
        if start is not None and end is not None:
            wanted = [
                start + timedelta(days=offset)
                for offset in range((end - start).days + 1)
            ]
        else:
            wanted = [day or min(days)]
        prices = [
            entry for d in wanted for entry in price_entries(d, days.get(d, []))
        ]
        return {"zone": zone, "unit": "dkk_per_kwh", "prices": prices}

    return _fake


def mock_entry(operator: str | None = "trefor-el-net", zone: str = "dk1") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{zone}_{operator or 'none'}",
        data={"api_key": "key", "zone": zone, "operator": operator},
    )
