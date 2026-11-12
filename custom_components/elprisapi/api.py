"""API client for data.elprisapi.dk."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp

from .const import API_BASE, API_KEY_HEADER, REQUEST_TIMEOUT

# Zones and operator slugs end up in the URL path, so only accept the
# characters the API itself documents for them.
_PATH_SEGMENT = re.compile(r"[a-z0-9-]+")


class ElprisApiError(Exception):
    """Base error for the Elpris API client."""


class ElprisApiAuthError(ElprisApiError):
    """The API key was rejected."""


class ElprisApiConnectionError(ElprisApiError):
    """The API could not be reached or timed out."""


def _segment(value: str, what: str) -> str:
    if not _PATH_SEGMENT.fullmatch(value):
        raise ElprisApiError(f"Invalid {what}: {value!r}")
    return value


@dataclass(frozen=True)
class ElprisApiClient:
    """Minimal async client for the endpoints this integration needs."""

    session: aiohttp.ClientSession
    api_key: str
    base_url: str = API_BASE

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self.session.get(
                    url, headers={API_KEY_HEADER: self.api_key}, params=params
                )
                try:
                    if response.status in (401, 403):
                        raise ElprisApiAuthError(
                            f"API key rejected (HTTP {response.status})"
                        )
                    if response.status >= 400:
                        body = await response.text()
                        raise ElprisApiError(
                            f"HTTP {response.status} for {path}: {body[:200]}"
                        )
                    return await response.json()
                finally:
                    # Hand the connection back on every path, including the
                    # early raises above that never read the body.
                    response.release()
        except TimeoutError as err:
            raise ElprisApiConnectionError(f"Timeout requesting {path}") from err
        except aiohttp.ClientError as err:
            raise ElprisApiConnectionError(f"Error requesting {path}: {err}") from err
        except ValueError as err:
            raise ElprisApiError(f"Invalid JSON from {path}: {err}") from err

    async def async_get_prices(
        self,
        zone: str,
        operator: str | None,
        day: date | None = None,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        """Fetch hourly prices in DKK/kWh.

        Without ``day`` the API returns today (Danish calendar day). With
        ``start`` and ``end`` it returns every published hour in that
        inclusive range, and ``day`` is ignored by the API.

        Tomorrow's prices are published around 13:00 Danish time; before that
        the API returns an empty ``prices`` list rather than an error.
        """
        path = f"/api/v1/prices/{_segment(zone, 'zone')}"
        if operator:
            path = f"{path}/{_segment(operator, 'operator slug')}"
        params: dict[str, Any] = {"unit": "dkk"}
        if start is not None and end is not None:
            params["start"] = start.isoformat()
            params["end"] = end.isoformat()
        elif day is not None:
            params["date"] = day.isoformat()
        return await self._get(path, params)

    async def async_get_operator(self, slug: str) -> dict[str, Any]:
        """Fetch a single grid operator, including current hourly tariffs."""
        return await self._get(f"/api/v1/operators/{_segment(slug, 'operator slug')}")

    async def async_get_operators(self) -> dict[str, Any]:
        """Fetch every known grid operator slug and name."""
        return await self._get("/api/v1/operators")

    async def async_get_health(self) -> dict[str, Any]:
        """Unauthenticated health probe used during setup."""
        return await self._get("/api/v1/health")
