"""Tests for the HTTP client against a mocked aiohttp session."""

from __future__ import annotations

from datetime import date

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.elprisapi import api

BASE = "https://data.elprisapi.dk/api/v1"


@pytest.fixture
def client(hass: HomeAssistant, aioclient_mock) -> api.ElprisApiClient:
    return api.ElprisApiClient(session=async_get_clientsession(hass), api_key="secret")


async def test_single_day_request(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}/prices/dk1/n1", json={"prices": []})

    assert await client.async_get_prices("dk1", "n1", date(2026, 11, 13)) == {"prices": []}

    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert headers == {"X-Api-Key": "secret"}
    assert aioclient_mock.mock_calls[0][1].query == {"unit": "dkk", "date": "2026-11-13"}


async def test_range_request_without_operator(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}/prices/dk2", json={"prices": []})

    await client.async_get_prices(
        "dk2", None, start=date(2026, 11, 12), end=date(2026, 11, 13)
    )

    assert aioclient_mock.mock_calls[0][1].query == {
        "unit": "dkk",
        "start": "2026-11-12",
        "end": "2026-11-13",
    }


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_key(client, aioclient_mock, status) -> None:
    aioclient_mock.get(f"{BASE}/operators", status=status, json={"error": "nope"})
    with pytest.raises(api.ElprisApiAuthError):
        await client.async_get_operators()


async def test_http_error_is_not_a_connection_error(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}/prices/dk1/nope", status=404, text="Unknown operator")
    with pytest.raises(api.ElprisApiError) as err:
        await client.async_get_prices("dk1", "nope")
    assert not isinstance(err.value, api.ElprisApiConnectionError)
    assert "404" in str(err.value)


async def test_timeout_is_a_connection_error(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}/health", exc=TimeoutError())
    with pytest.raises(api.ElprisApiConnectionError):
        await client.async_get_health()


async def test_invalid_json(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}/health", text="<html>oops</html>")
    with pytest.raises(api.ElprisApiError):
        await client.async_get_health()


@pytest.mark.parametrize("operator", ["../health", "N1", "n1/x", "n1?x=1", " "])
async def test_bad_operator_slug_never_reaches_the_network(
    client, aioclient_mock, operator
) -> None:
    with pytest.raises(api.ElprisApiError):
        await client.async_get_prices("dk1", operator)
    with pytest.raises(api.ElprisApiError):
        await client.async_get_operator(operator)
    assert aioclient_mock.call_count == 0
