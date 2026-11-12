"""Coordinator for the Elpris API integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ElprisApiAuthError,
    ElprisApiClient,
    ElprisApiConnectionError,
    ElprisApiError,
)
from .const import (
    CONF_API_KEY,
    CONF_OPERATOR,
    CONF_ZONE,
    DANISH_TZ,
    DOMAIN,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_WAITING,
    TOMORROW_EXPECTED_FROM_HOUR,
)
from .pricing import (
    build_slots,
    current_slot,
    parse_hour,
    slots_for_date,
    stats_for_date,
)

_LOGGER = logging.getLogger(__name__)

type ElprisApiConfigEntry = ConfigEntry[ElprisApiCoordinator]


@dataclass
class ElprisApiData:
    """Everything the sensors need, as of the moment ``now``."""

    zone: str
    operator: str | None
    slots: list[dict[str, Any]]
    now: datetime
    today_stats: dict[str, float] | None = None
    tomorrow_stats: dict[str, float] | None = None
    today_slots: list[dict[str, Any]] = field(default_factory=list)
    tomorrow_slots: list[dict[str, Any]] = field(default_factory=list)

    @property
    def current(self) -> dict[str, Any] | None:
        """The slot covering now."""
        return current_slot(self.slots, self.now)

    @property
    def current_breakdown(self) -> dict[str, Any] | None:
        """The price components of the slot covering now.

        ``current`` is a slot (start/end/breakdown); sensors read components
        from this, not from the slot itself.
        """
        slot = self.current
        if slot is None:
            return None
        return slot.get("breakdown")

    @property
    def tomorrow_available(self) -> bool:
        """Whether tomorrow's prices have been published yet."""
        return bool(self.tomorrow_slots)


class ElprisApiCoordinator(DataUpdateCoordinator[ElprisApiData]):
    """Fetch today's and tomorrow's prices and keep them cached.

    Polling and the clock are decoupled: prices are cached per hour stamp,
    and ``async_handle_clock_tick`` re-derives the sensor values from that
    cache as time passes. A failed poll therefore does not take the sensors
    down as long as the cache still covers the current time.
    """

    config_entry: ElprisApiConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ElprisApiConfigEntry) -> None:
        """Initialise the coordinator from a config entry."""
        self.zone: str = entry.data[CONF_ZONE]
        self.operator: str | None = entry.data.get(CONF_OPERATOR)
        self._client = ElprisApiClient(
            session=async_get_clientsession(hass), api_key=entry.data[CONF_API_KEY]
        )
        # Raw API price entries keyed by their ``hour`` stamp (offset included,
        # so the two 02:00 entries on the autumn switch day stay distinct).
        self._entries: dict[str, dict[str, Any]] = {}
        self._tz: tzinfo | None = None
        self._serving_cache = False
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL_WAITING,
        )

    async def _async_update_data(self) -> ElprisApiData:
        """Fetch prices for today and tomorrow and derive the sensor values."""
        if self._tz is None:
            self._tz = await dt_util.async_get_time_zone(DANISH_TZ)
        today = datetime.now(self._tz).date()

        try:
            payload = await self._async_fetch(today, today + timedelta(days=1))
        except ElprisApiAuthError as err:
            raise ConfigEntryAuthFailed(f"API key rejected: {err}") from err
        except ElprisApiError as err:
            return self._data_from_cache_or_fail(err)

        prices = payload.get("prices") if isinstance(payload, dict) else None
        for entry in prices or []:
            if isinstance(entry, dict) and isinstance(entry.get("hour"), str):
                self._entries[entry["hour"]] = entry

        try:
            data = self._build_data()
        except (TypeError, ValueError) as err:
            self._entries.clear()
            raise UpdateFailed(f"Unexpected price data from Elpris API: {err}") from err

        if not data.slots:
            raise UpdateFailed("Elpris API returned no prices for this zone/operator")

        if self._serving_cache:
            _LOGGER.info("Elpris API is reachable again")
            self._serving_cache = False

        waiting = (
            not data.tomorrow_available
            and data.now.hour >= TOMORROW_EXPECTED_FROM_HOUR
        )
        self.update_interval = SCAN_INTERVAL_WAITING if waiting else SCAN_INTERVAL_IDLE
        return data

    async def _async_fetch(self, today: date, tomorrow: date) -> dict[str, Any]:
        """Fetch both days in one request, falling back to today only.

        The fallback covers the API rejecting a range whose end is not
        published yet; connection and auth problems are not retried.
        """
        try:
            return await self._client.async_get_prices(
                self.zone, self.operator, start=today, end=tomorrow
            )
        except (ElprisApiAuthError, ElprisApiConnectionError):
            raise
        except ElprisApiError as err:
            _LOGGER.debug("Range request failed (%s); fetching today only", err)
            return await self._client.async_get_prices(self.zone, self.operator)

    def _data_from_cache_or_fail(self, err: ElprisApiError) -> ElprisApiData:
        """Keep serving cached prices through an outage while they last."""
        data = self._build_data()
        if data.current is None:
            raise UpdateFailed(str(err)) from err
        if not self._serving_cache:
            _LOGGER.warning(
                "Elpris API request failed, using cached prices meanwhile: %s", err
            )
            self._serving_cache = True
        self.update_interval = SCAN_INTERVAL_WAITING
        return data

    def _build_data(self) -> ElprisApiData:
        """Derive the sensor values from the cache for the current time."""
        tz = self._tz
        assert tz is not None
        now = datetime.now(tz)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        # Yesterday's prices are of no use once the Danish day has rolled over.
        self._entries = {
            hour: entry
            for hour, entry in self._entries.items()
            if parse_hour(hour).astimezone(tz).date() >= today
        }
        slots = build_slots(self._entries.values())

        return ElprisApiData(
            zone=self.zone,
            operator=self.operator,
            slots=slots,
            now=now,
            today_stats=stats_for_date(slots, today, tz),
            tomorrow_stats=stats_for_date(slots, tomorrow, tz),
            today_slots=slots_for_date(slots, today, tz),
            tomorrow_slots=slots_for_date(slots, tomorrow, tz),
        )

    @callback
    def async_handle_clock_tick(self, _now: datetime | None = None) -> None:
        """Re-derive the sensor values from cached prices as time passes."""
        if self.data is None or self._tz is None:
            return
        self.data = self._build_data()
        self.async_update_listeners()
