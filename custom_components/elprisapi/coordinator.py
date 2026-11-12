"""Coordinator for the Elpris API integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ElprisApiAuthError, ElprisApiClient, ElprisApiError
from .const import (
    CONF_API_KEY,
    CONF_OPERATOR,
    CONF_ZONE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .pricing import build_slots, current_slot, slots_for_date, stats_for_date

_LOGGER = logging.getLogger(__name__)


@dataclass
class ElprisApiData:
    """Everything the sensors need, computed once per refresh."""

    zone: str
    operator: str | None
    unit: str
    slots: list[dict[str, Any]]
    now: datetime
    today_stats: dict[str, float] | None = None
    tomorrow_stats: dict[str, float] | None = None
    today_slots: list[dict[str, Any]] = field(default_factory=list)
    tomorrow_slots: list[dict[str, Any]] = field(default_factory=list)

    @property
    def current(self) -> dict[str, Any] | None:
        """The hourly slot covering now."""
        return current_slot(self.slots, self.now)

    @property
    def tomorrow_available(self) -> bool:
        """Whether tomorrow's prices have been published yet."""
        return bool(self.tomorrow_slots)


class ElprisApiCoordinator(DataUpdateCoordinator[ElprisApiData]):
    """Fetch today's and tomorrow's prices on a schedule."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator from a config entry."""
        self.zone: str = entry.data[CONF_ZONE]
        self.operator: str | None = entry.data.get(CONF_OPERATOR)
        self._client = ElprisApiClient(
            session=async_get_clientsession(hass), api_key=entry.data[CONF_API_KEY]
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> ElprisApiData:
        """Fetch prices for today and tomorrow and derive the sensor values."""
        today = dt_util.now().date()
        tomorrow = today + timedelta(days=1)

        try:
            today_payload = await self._client.async_get_prices(self.zone, self.operator)
            try:
                tomorrow_payload = await self._client.async_get_prices(
                    self.zone, self.operator, day=tomorrow
                )
            except ElprisApiError as err:
                # Tomorrow's data being unavailable must not break today's
                # sensors; they are simply reported as not-yet-available.
                _LOGGER.debug("Tomorrow prices unavailable: %s", err)
                tomorrow_payload = {"prices": []}
        except ElprisApiAuthError as err:
            raise UpdateFailed(f"API key rejected: {err}") from err
        except ElprisApiError as err:
            raise UpdateFailed(str(err)) from err

        slots = build_slots(today_payload.get("prices") or [])
        slots += build_slots(tomorrow_payload.get("prices") or [])

        if not slots:
            raise UpdateFailed(
                "Elpris API returned no prices for this zone/operator"
            )

        now = dt_util.now()
        tz = dt_util.get_default_time_zone()

        return ElprisApiData(
            zone=self.zone,
            operator=self.operator,
            unit=today_payload.get("unit", "dkk_per_kwh"),
            slots=slots,
            now=now,
            today_stats=stats_for_date(slots, today, tz),
            tomorrow_stats=stats_for_date(slots, tomorrow, tz),
            today_slots=slots_for_date(slots, today, tz),
            tomorrow_slots=slots_for_date(slots, tomorrow, tz),
        )
