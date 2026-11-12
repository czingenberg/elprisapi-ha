"""Live smoke test against data.elprisapi.dk using the real client.

Run: .venv/bin/python tests/live_check.py
Requires the API key in the ELPRIS_API_KEY env var or the file ~/elapi.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components"))

import importlib.util  # noqa: E402


def _load_module(name: str):
    """Load an integration module with its relative imports intact."""
    pkg_dir = Path(__file__).parents[1] / "custom_components" / "elprisapi"
    spec = importlib.util.spec_from_file_location(
        f"elprisapi.{name}", pkg_dir / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"elprisapi.{name}"] = module
    spec.loader.exec_module(module)
    return module


_ensure_pkg = importlib.util.spec_from_file_location(
    "elprisapi", Path(__file__).parents[1] / "custom_components" / "elprisapi" / "__init__.py"
)
_pkg = importlib.util.module_from_spec(_ensure_pkg)
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "elprisapi")]
sys.modules["elprisapi"] = _pkg

api = _load_module("api")
pricing = _load_module("pricing")

ElprisApiClient = api.ElprisApiClient
build_slots = pricing.build_slots
current_slot = pricing.current_slot
forecast_attribute = pricing.forecast_attribute
stats_for_date = pricing.stats_for_date

from zoneinfo import ZoneInfo  # noqa: E402

CPH = ZoneInfo("Europe/Copenhagen")


def load_key() -> str:
    if key := os.environ.get("ELPRIS_API_KEY"):
        return key.strip()
    return (Path.home() / "elapi").read_text().strip()


async def main() -> int:
    key = load_key()
    zone = os.environ.get("ELPRIS_ZONE", "dk1")
    operator = os.environ.get("ELPRIS_OPERATOR", "trefor-el-net")

    async with aiohttp.ClientSession() as session:
        client = ElprisApiClient(session=session, api_key=key)

        health = await client.async_get_health()
        print(f"health          : {health['status']} (latest spot {health.get('latest_spot_date')})")

        # "Today" is the Danish calendar day, whatever this machine's timezone.
        now = datetime.now(CPH)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        today_payload = await client.async_get_prices(zone, operator)
        tomorrow_payload = await client.async_get_prices(zone, operator, day=tomorrow)

        # The integration fetches both days in one range request; it must
        # return exactly what the two single-day requests return.
        range_payload = await client.async_get_prices(
            zone, operator, start=today, end=tomorrow
        )
        assert range_payload["prices"] == (
            today_payload["prices"] + tomorrow_payload["prices"]
        ), "range request differs from the two single-day requests"
        print("range request   : OK (matches today + tomorrow)")

        print(f"unit            : {today_payload['unit']}")
        print(f"today entries   : {len(today_payload['prices'])}")
        print(f"tomorrow entries: {len(tomorrow_payload['prices'])}")

        slots = build_slots(today_payload["prices"]) + build_slots(
            tomorrow_payload["prices"]
        )
        cur = current_slot(slots, now)
        if cur is None:
            print("current         : OUTSIDE DATA WINDOW", file=sys.stderr)
            return 1

        b = cur["breakdown"]
        print(f"current hour    : {cur['start'].isoformat()} -> {cur['end'].isoformat()}")
        for key_name in (
            "spot_price",
            "electricity_tax",
            "system_tariff",
            "transmission_tariff",
            "grid_tariff",
            "total_excl_vat",
            "vat",
            "total",
        ):
            print(f"  {key_name:22s}: {b.get(key_name)}")

        # The breakdown must add up, otherwise the API or our maths is wrong.
        parts = (
            b["spot_price"]
            + b["electricity_tax"]
            + b["system_tariff"]
            + b["transmission_tariff"]
            + b["grid_tariff"]
        )
        assert abs(parts - b["total_excl_vat"]) < 0.02, (parts, b["total_excl_vat"])
        assert abs(b["total_excl_vat"] * 0.25 - b["vat"]) < 0.02, b
        assert abs(b["total_excl_vat"] + b["vat"] - b["total"]) < 0.02, b
        print("breakdown maths : OK (sums and 25% VAT reconcile)")

        for label, day in (("today", today), ("tomorrow", tomorrow)):
            stats = stats_for_date(slots, day, CPH)
            print(f"{label:15s}   : {stats}")

        print(f"forecast length : {len(forecast_attribute(slots))}")

        operators = await client.async_get_operators()
        slugs = [o["slug"] for o in operators["operators"]]
        assert operator in slugs, f"{operator} not in operator list"
        print(f"operator list   : {len(slugs)} operators")

        op = await client.async_get_operator(operator)
        print(f"operator        : {op['name']} ({op['company']}) GLN {op.get('gln_number')}")
        print(f"tariff slots    : {len(op.get('current_tariff_prices') or [])} hourly values")
        return 0


sys.exit(asyncio.run(main()))
