"""API client for data.elprisapi.dk."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp

from .const import API_BASE, API_KEY_HEADER, REQUEST_TIMEOUT


class ElprisApiError(Exception):
    """Base error for the Elpris API client."""


class ElprisApiAuthError(ElprisApiError):
    """The API key was rejected."""


class ElprisApiConnectionError(ElprisApiError):
    """The API could not be reached or timed out."""


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
        except TimeoutError as err:
            raise ElprisApiConnectionError(f"Timeout requesting {path}") from err
        except aiohttp.ClientError as err:
            raise ElprisApiConnectionError(f"Error requesting {path}: {err}") from err

    async def async_get_prices(
        self, zone: str, operator: str | None, day: date | None = None
    ) -> dict[str, Any]:
        """Fetch hourly prices in DKK/kWh.

        Without ``day`` the API returns today (Danish calendar day).
        Tomorrow's prices are published around 13:00 Danish time; before that
        the API returns an empty ``prices`` list rather than an error.
        """
        path = f"/api/v1/prices/{zone}"
        if operator:
            path = f"{path}/{operator}"
        params: dict[str, Any] = {"unit": "dkk"}
        if day is not None:
            params["date"] = day.isoformat()
        return await self._get(path, params)

    async def async_get_operator(self, slug: str) -> dict[str, Any]:
        """Fetch a single grid operator, including current hourly tariffs."""
        return await self._get(f"/api/v1/operators/{slug}")

    async def async_get_operators(self) -> dict[str, Any]:
        """Fetch every known grid operator slug and name."""
        return await self._get("/api/v1/operators")

    async def async_get_health(self) -> dict[str, Any]:
        """Unauthenticated health probe used during setup."""
        return await self._get("/api/v1/health")
