"""Validate the integration's static shape against a real Home Assistant install.

Catches bad entity descriptions, translation gaps and manifest problems that
the behavioural tests cannot see.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import voluptuous as vol

from custom_components.elprisapi import binary_sensor, config_flow, const, sensor


def _walk_strings(node: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten a translation tree into (path, string) pairs."""
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(_walk_strings(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_walk_strings(value, f"{prefix}[{index}]"))
    elif isinstance(node, str):
        out.append((prefix, node))
    return out

ROOT = Path(__file__).parents[1]
COMPONENT_DIR = ROOT / "custom_components" / "elprisapi"
KEY_URL = "https://elprisapi.dk/#api-noegle"
REPO_URL = "https://github.com/czingenberg/elprisapi-ha"

MANIFEST = json.loads((COMPONENT_DIR / "manifest.json").read_text())
STRINGS = json.loads((COMPONENT_DIR / "strings.json").read_text())
SENSOR_KEYS = [description.key for description in sensor.SENSORS]


def test_manifest() -> None:
    required = {"domain", "name", "version", "config_flow", "iot_class", "documentation"}
    assert required <= set(MANIFEST)
    assert MANIFEST["domain"] == COMPONENT_DIR.name == const.DOMAIN
    assert MANIFEST["config_flow"] is True
    assert MANIFEST["iot_class"] == "cloud_polling"
    assert MANIFEST["requirements"] == []


def test_manifest_points_at_this_repository() -> None:
    assert MANIFEST["issue_tracker"] == f"{REPO_URL}/issues"
    assert MANIFEST["codeowners"] == ["@czingenberg"]
    assert REPO_URL in (ROOT / "README.md").read_text()


def test_english_translation_matches_strings() -> None:
    en = json.loads((COMPONENT_DIR / "translations" / "en.json").read_text())
    assert en == STRINGS


def test_config_flow_strings_cover_the_flow() -> None:
    steps = STRINGS["config"]["step"]
    assert set(steps) == {"user", "operator", "reauth_confirm"}
    assert set(steps["user"]["data"]) == {"api_key", "zone"}
    assert set(steps["operator"]["data"]) == {"operator"}
    assert set(steps["reauth_confirm"]["data"]) == {"api_key"}
    assert set(STRINGS["config"]["error"]) == {
        "invalid_auth",
        "cannot_connect",
        "no_data",
        "unknown",
    }
    assert set(STRINGS["config"]["abort"]) == {"already_configured", "reauth_successful"}


def test_key_page_is_linked_where_it_is_needed() -> None:
    """The setup form is where someone needs the link; losing it sends users hunting.

    Home Assistant's hassfest rejects URLs inside translation strings, so the
    forms carry a ``{key_url}`` placeholder and the flow supplies the value.
    Assert both halves: the placeholder in the strings, and the URL in the flow
    and the README.
    """
    user_step = STRINGS["config"]["step"]["user"]
    assert "{key_url}" in user_step["description"]
    assert "{key_url}" in user_step["data_description"]["api_key"]
    assert "{key_url}" in STRINGS["config"]["step"]["reauth_confirm"]["description"]

    # No bare URL may appear in any translated string.
    for path, value in _walk_strings(STRINGS):
        assert "http://" not in value and "https://" not in value, (
            f"URL in translation string at {path}; use a description placeholder"
        )

    assert KEY_URL in (ROOT / "README.md").read_text()
    assert config_flow.KEY_URL == KEY_URL


def test_sensor_descriptions() -> None:
    assert len(SENSOR_KEYS) == len(set(SENSOR_KEYS)) == 16
    assert set(SENSOR_KEYS) == set(STRINGS["entity"]["sensor"])
    assert binary_sensor.TOMORROW_AVAILABLE.key in STRINGS["entity"]["binary_sensor"]


@pytest.mark.parametrize("description", sensor.SENSORS, ids=SENSOR_KEYS)
def test_sensor_description(description) -> None:
    assert description.translation_key == description.key
    assert description.native_unit_of_measurement == "DKK/kWh"
    assert callable(description.value_fn)


def test_config_flow_schema_requires_input() -> None:
    with pytest.raises(vol.Invalid):
        config_flow.STEP_USER_SCHEMA({})


def test_constants() -> None:
    assert const.ZONES == ["dk1", "dk2"]
    assert const.DEFAULT_ZONE in const.ZONES
    assert not const.API_BASE.endswith("/")
    assert const.SCAN_INTERVAL_WAITING < const.SCAN_INTERVAL_IDLE
