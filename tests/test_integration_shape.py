"""Validate the integration's static shape against a real Home Assistant install.

Catches bad entity descriptions, translation gaps and manifest problems that
the behavioural tests cannot see.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import voluptuous as vol

from custom_components.elprisapi import binary_sensor, config_flow, const, sensor

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
    """The setup form is where someone needs the link; losing it sends users hunting."""
    user_step = STRINGS["config"]["step"]["user"]
    assert KEY_URL in user_step["description"]
    assert KEY_URL in user_step["data_description"]["api_key"]
    assert KEY_URL in STRINGS["config"]["step"]["reauth_confirm"]["description"]
    assert KEY_URL in (ROOT / "README.md").read_text()


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
