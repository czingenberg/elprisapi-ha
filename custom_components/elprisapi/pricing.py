"""Pure price logic for the Elpris API integration.

Deliberately free of Home Assistant imports so it can be unit tested
standalone. Everything here works on the API's own JSON payload shape.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

# Price components exposed by the API, in display order.
COMPONENTS: tuple[str, ...] = (
    "spot_price",
    "electricity_tax",
    "system_tariff",
    "transmission_tariff",
    "grid_tariff",
    "total_excl_vat",
    "vat",
    "total",
)


def parse_hour(value: str) -> datetime:
    """Parse an API hour stamp such as '2026-11-12T00:00:00+01:00'."""
    return datetime.fromisoformat(value)


def build_slots(
    prices: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn the raw ``prices`` array into ordered hourly slots.

    On daylight saving switch days the API returns 23 or 25 entries and the
    two 02:00 entries differ only by their UTC offset; sorting on the aware
    datetime keeps them in the right absolute order.
    """
    slots: list[dict[str, Any]] = []
    for entry in prices:
        start = parse_hour(entry["hour"])
        slots.append(
            {
                "start": start,
                "end": start + timedelta(hours=1),
                "breakdown": {
                    key: _as_float(entry.get(key))
                    for key in COMPONENTS
                    if entry.get(key) is not None
                },
            }
        )
    slots.sort(key=lambda slot: slot["start"])
    return slots


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def current_slot(
    slots: Iterable[dict[str, Any]], now: datetime
) -> dict[str, Any] | None:
    """Return the slot covering ``now``, or None if outside the data window."""
    for slot in slots:
        if slot["start"] <= now < slot["end"]:
            return slot
    return None


def slots_for_date(
    slots: Iterable[dict[str, Any]], day: date, tz: Any
) -> list[dict[str, Any]]:
    """Slots belonging to a Danish calendar day."""
    return [
        slot for slot in slots if slot["start"].astimezone(tz).date() == day
    ]


def stats_for_date(
    slots: Iterable[dict[str, Any]], day: date, tz: Any
) -> dict[str, float] | None:
    """Min/mean/max of the total price for one calendar day.

    Returns None when the day has no prices (tomorrow before ~13:00).
    """
    totals = [
        slot["breakdown"]["total"]
        for slot in slots_for_date(slots, day, tz)
        if slot["breakdown"].get("total") is not None
    ]
    if not totals:
        return None
    return {
        "min": min(totals),
        "mean": sum(totals) / len(totals),
        "max": max(totals),
    }


def forecast_attribute(
    slots: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Forecast list in the shape Strømligning uses.

    Keeping this format means existing dashboards and automations written for
    the ``stromligning`` integration keep working unchanged.
    """
    return [
        {
            "price": slot["breakdown"].get("total"),
            "start": slot["start"].isoformat(),
            "end": slot["end"].isoformat(),
        }
        for slot in slots
    ]
