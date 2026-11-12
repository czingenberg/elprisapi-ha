"""Tests for the pure pricing helpers."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "elprisapi"))

from pricing import (  # noqa: E402
    build_slots,
    current_slot,
    forecast_attribute,
    slots_for_date,
    stats_for_date,
)

CPH = ZoneInfo("Europe/Copenhagen")


def _entry(hour: str, total: float, **extra) -> dict:
    base = {
        "hour": hour,
        "spot_price": total - 10,
        "electricity_tax": 0.8,
        "system_tariff": 7.2,
        "transmission_tariff": 4.3,
        "total_excl_vat": total - 5,
        "vat": 5.0,
        "total": total,
    }
    base.update(extra)
    return base


def test_build_slots_orders_and_computes_end():
    slots = build_slots(
        [_entry("2026-11-12T02:00:00+01:00", 200.0), _entry("2026-11-12T00:00:00+01:00", 100.0)]
    )
    assert [s["breakdown"]["total"] for s in slots] == [100.0, 200.0]
    assert slots[0]["end"] - slots[0]["start"] == timedelta(hours=1)


def test_current_slot_inside_and_outside():
    slots = build_slots([_entry("2026-11-12T13:00:00+01:00", 150.0)])
    inside = datetime(2026, 11, 12, 13, 30, tzinfo=CPH)
    outside = datetime(2026, 11, 12, 14, 30, tzinfo=CPH)
    assert current_slot(slots, inside)["breakdown"]["total"] == 150.0
    assert current_slot(slots, outside) is None


def test_stats_for_date_none_when_empty():
    slots = build_slots([_entry("2026-11-12T00:00:00+01:00", 100.0)])
    assert stats_for_date(slots, date(2026, 11, 13), CPH) is None


def test_stats_for_date_ignores_other_days():
    slots = build_slots(
        [
            _entry("2026-11-12T00:00:00+01:00", 100.0),
            _entry("2026-11-12T01:00:00+01:00", 300.0),
            _entry("2026-11-13T00:00:00+01:00", 999.0),
        ]
    )
    stats = stats_for_date(slots, date(2026, 11, 12), CPH)
    assert stats == {"min": 100.0, "mean": 200.0, "max": 300.0}


def test_daylight_saving_day_has_25_slots():
    # 2026-10-25 is the autumn switch: 02:00 occurs twice.
    entries = [
        _entry("2026-10-25T01:00:00+02:00", 10.0),
        _entry("2026-10-25T02:00:00+02:00", 11.0),
        _entry("2026-10-25T02:00:00+01:00", 12.0),
        _entry("2026-10-25T03:00:00+01:00", 13.0),
    ]
    slots = build_slots(entries)
    # Both 02:00 entries survive and are ordered by absolute time.
    assert len(slots) == 4
    assert [s["breakdown"]["total"] for s in slots] == [10.0, 11.0, 12.0, 13.0]
    assert len({s["start"] for s in slots}) == 4


def test_current_slot_distinguishes_the_two_0200_hours():
    entries = [
        _entry("2026-10-25T02:00:00+02:00", 11.0),
        _entry("2026-10-25T02:00:00+01:00", 12.0),
    ]
    slots = build_slots(entries)
    first = datetime(2026, 10, 25, 2, 30, tzinfo=timezone(timedelta(hours=2)))
    second = datetime(2026, 10, 25, 2, 30, tzinfo=timezone(timedelta(hours=1)))
    assert current_slot(slots, first)["breakdown"]["total"] == 11.0
    assert current_slot(slots, second)["breakdown"]["total"] == 12.0


def test_forecast_attribute_shape_matches_stromligning():
    slots = build_slots([_entry("2026-11-12T13:00:00+01:00", 150.0)])
    forecast = forecast_attribute(slots)[0]
    assert set(forecast) == {"price", "start", "end"}
    assert forecast["price"] == 150.0
    assert forecast["start"].startswith("2026-11-12T13:00:00")


def test_missing_components_are_tolerated():
    slots = build_slots(
        [{"hour": "2026-11-12T00:00:00+01:00", "total": 100.0}]  # no grid_tariff
    )
    assert slots[0]["breakdown"]["total"] == 100.0
    assert "grid_tariff" not in slots[0]["breakdown"]


def test_slots_for_date_filters():
    slots = build_slots(
        [
            _entry("2026-11-12T23:00:00+01:00", 100.0),
            _entry("2026-11-13T00:00:00+01:00", 200.0),
        ]
    )
    assert len(slots_for_date(slots, date(2026, 11, 12), CPH)) == 1
    assert len(slots_for_date(slots, date(2026, 11, 13), CPH)) == 1
