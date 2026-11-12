"""Validate the integration modules against a real Home Assistant install.

Catches import errors, bad entity descriptions, translation gaps and
manifest problems that the pure pricing tests cannot see.

Run: .venv/bin/python tests/test_integration_shape.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "elprisapi"
sys.path.insert(0, str(COMPONENT_DIR.parents[1]))

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        failures.append(label)


print("manifest.json")
manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text())
required = {"domain", "name", "version", "config_flow", "iot_class", "documentation"}
check("required keys present", required <= set(manifest), str(required - set(manifest)))
check("domain matches folder", manifest["domain"] == COMPONENT_DIR.name)
check("config_flow enabled", manifest["config_flow"] is True)
check("iot_class is cloud_polling", manifest["iot_class"] == "cloud_polling")
check("no requirements needed", manifest["requirements"] == [])

print("\nstrings / translations")
strings = json.loads((COMPONENT_DIR / "strings.json").read_text())
en = json.loads((COMPONENT_DIR / "translations" / "en.json").read_text())
check("en.json matches strings.json", strings == en)
check("config step user exists", "user" in strings["config"]["step"])
form_fields = set(strings["config"]["step"]["user"]["data"])
check(
    "form fields cover flow schema",
    {"api_key", "zone", "operator"} <= form_fields,
    str(form_fields),
)
check(
    "all error keys translated",
    {"invalid_auth", "cannot_connect", "no_data", "unknown"}
    <= set(strings["config"]["error"]),
)
check(
    "abort already_configured translated",
    "already_configured" in strings["config"]["abort"],
)

print("\nmodule imports")
from custom_components.elprisapi import api, binary_sensor, config_flow, const, coordinator, pricing, sensor  # noqa: E402

check("api imports", hasattr(api, "ElprisApiClient"))
check("coordinator imports", hasattr(coordinator, "ElprisApiCoordinator"))
check("sensor imports", hasattr(sensor, "async_setup_entry"))
check("binary_sensor imports", hasattr(binary_sensor, "async_setup_entry"))
check("config_flow imports", hasattr(config_flow, "ElprisApiConfigFlow"))

print("\nsensor descriptions")
descriptions = sensor.SENSORS
keys = [d.key for d in descriptions]
check("sensor keys unique", len(keys) == len(set(keys)), str(keys))
check("16 sensors defined", len(descriptions) == 16, str(len(descriptions)))

translated = set(strings["entity"]["sensor"])
check(
    "every sensor has a translation",
    set(keys) <= translated,
    str(set(keys) - translated),
)
check(
    "no orphan sensor translations",
    translated <= set(keys),
    str(translated - set(keys)),
)
for d in descriptions:
    check(f"{d.key}: has translation_key", d.translation_key == d.key)
    check(f"{d.key}: readable callable", callable(d.value_fn))

binary_keys = {binary_sensor.TOMORROW_AVAILABLE.key}
check(
    "binary sensor translated",
    binary_keys <= set(strings["entity"]["binary_sensor"]),
)

print("\nmonetary sensors declare device_class + unit")
for d in descriptions:
    if d.device_class is not None:
        check(f"{d.key}: has unit", bool(d.native_unit_of_measurement))

print("\nconfig flow schema builds")
schema = config_flow.STEP_USER_SCHEMA
try:
    schema({})
except Exception as err:  # noqa: BLE001 - expected: required keys missing
    check("schema rejects empty input", "required" in str(err).lower() or "required key" in str(err), str(err))
else:
    check("schema rejects empty input", False, "empty dict accepted")

print("\nconst sanity")
check("zones are dk1/dk2", const.ZONES == ["dk1", "dk2"])
check("default zone is dk1", const.DEFAULT_ZONE == "dk1")
check("api base has no trailing slash", not const.API_BASE.endswith("/"))
check("scan interval is a timedelta", const.DEFAULT_SCAN_INTERVAL.total_seconds() > 0)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All integration shape checks passed.")
