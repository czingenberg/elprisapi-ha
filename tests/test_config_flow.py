"""Tests for the config flow: setup, operator choice, errors and reauth.

The first version of this integration crashed with ``KeyError: 'today'`` in
production because config_flow expected a dict shape that
``api.async_get_prices`` no longer returned after a refactor. These tests pin
the contract between the two modules and use the real Home Assistant test
harness so the flow runs exactly as it does live.
"""

from __future__ import annotations

from contextlib import contextmanager
import re
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.elprisapi import api
from custom_components.elprisapi.const import DOMAIN

from helpers import mock_entry

OPERATORS = {
    "operators": [
        {"slug": "trefor-el-net", "name": "TREFOR El-net", "company": "TREFOR El-net A/S"},
        {"slug": "n1", "name": "N1", "company": "N1 A/S - 131"},
    ]
}
PRICES = {
    "zone": "dk1",
    "unit": "dkk_per_kwh",
    "date": "2026-11-12",
    "prices": [{"hour": "2026-11-12T00:00:00+01:00", "total": 1.85}],
}


@pytest.fixture(autouse=True)
def skip_entry_setup():
    """These tests exercise the flow, not the integration setup."""
    with patch("custom_components.elprisapi.async_setup_entry", return_value=True):
        yield


@contextmanager
def _api(operators=OPERATORS, prices=PRICES):
    """Patch the two client calls; pass an exception to make one fail."""

    def _mock(result):
        if isinstance(result, Exception):
            return {"side_effect": result}
        return {"return_value": result}

    with (
        patch.object(api.ElprisApiClient, "async_get_operators", **_mock(operators)),
        patch.object(api.ElprisApiClient, "async_get_prices", **_mock(prices)) as get_prices,
    ):
        yield get_prices


async def _start(hass: HomeAssistant, user_input: dict):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_full_flow_with_operator(hass: HomeAssistant) -> None:
    """Key and zone, then an operator picked from the API's list."""
    with _api() as get_prices:
        result = await _start(hass, {"api_key": " key ", "zone": "dk1"})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "operator"

        selector = result["data_schema"].schema["operator"]
        assert [option["value"] for option in selector.config["options"]] == [
            "none",
            "n1",
            "trefor-el-net",
        ]

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"operator": "trefor-el-net"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "api_key": "key",
        "zone": "dk1",
        "operator": "trefor-el-net",
    }
    assert "DK1" in result["title"]
    assert result["result"].unique_id == "dk1_trefor-el-net"
    get_prices.assert_awaited_once_with("dk1", "trefor-el-net")


async def test_flow_without_operator(hass: HomeAssistant) -> None:
    """"No grid operator" is stored as None."""
    with _api() as get_prices:
        result = await _start(hass, {"api_key": "key", "zone": "dk2"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"operator": "none"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["operator"] is None
    assert result["result"].unique_id == "dk2_none"
    get_prices.assert_awaited_once_with("dk2", None)


async def test_operator_must_come_from_the_list(hass: HomeAssistant) -> None:
    """Free text can no longer reach the API's URL path."""
    with _api():
        result = await _start(hass, {"api_key": "key", "zone": "dk1"})
        with pytest.raises(Exception):  # noqa: B017, PT011 - schema validation
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {"operator": "../health"}
            )


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (api.ElprisApiAuthError("401"), "invalid_auth"),
        (api.ElprisApiConnectionError("timeout"), "cannot_connect"),
        (api.ElprisApiError("HTTP 500"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_key_check_errors(hass: HomeAssistant, failure, error) -> None:
    """The key is checked in the first step, and the form can be retried."""
    with _api(operators=failure):
        result = await _start(hass, {"api_key": "bad", "zone": "dk1"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}

    with _api():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "good", "zone": "dk1"}
        )
    assert result["step_id"] == "operator"


@pytest.mark.parametrize(
    "prices",
    [
        {"zone": "dk1", "prices": []},
        api.ElprisApiError("HTTP 404 Unknown operator"),
    ],
)
async def test_no_prices_for_operator_is_no_data(hass: HomeAssistant, prices) -> None:
    """An empty or failing price lookup shows no_data rather than crashing."""
    with _api(prices=prices):
        result = await _start(hass, {"api_key": "key", "zone": "dk1"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"operator": "n1"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "operator"
    assert result["errors"] == {"base": "no_data"}


async def test_duplicate_zone_and_operator_aborts(hass: HomeAssistant) -> None:
    """Configuring the same zone/operator twice must abort."""
    mock_entry().add_to_hass(hass)

    with _api():
        result = await _start(hass, {"api_key": "key2", "zone": "dk1"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"operator": "trefor-el-net"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_the_key(hass: HomeAssistant) -> None:
    """A rejected key can be replaced without removing the entry."""
    entry = mock_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with _api(operators=api.ElprisApiAuthError("401")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "still-bad"}
        )
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["api_key"] == "key"

    with _api():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "new-key"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {"api_key": "new-key", "zone": "dk1", "operator": "trefor-el-net"}


async def test_form_supplies_the_key_url_placeholder(hass: HomeAssistant) -> None:
    """The form must hand the flow's URL to the translation placeholder.

    Home Assistant's hassfest forbids URLs inside translation strings, so the
    strings carry ``{key_url}`` and the flow supplies it. If that wiring is
    dropped the user sees a literal ``{key_url}`` in the dialog.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    placeholders = result["description_placeholders"]
    assert placeholders["key_url"] == "https://elprisapi.dk/#api-noegle"

    # Every placeholder used in the strings must be supplied, or the UI shows
    # the raw braces.
    import json
    from pathlib import Path

    strings = json.loads(
        (Path(__file__).parents[1] / "custom_components/elprisapi/strings.json").read_text()
    )
    used = set()
    for field in (
        strings["config"]["step"]["user"]["description"],
        strings["config"]["step"]["user"]["data_description"]["api_key"],
    ):
        used.update(re.findall(r"\{(\w+)\}", field))
    assert used <= set(placeholders), f"unsupplied placeholders: {used - set(placeholders)}"
