"""Constants for the Elpris API integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "elprisapi"
NAME = "Elpris API"
VERSION = "0.1.1"

API_BASE = "https://data.elprisapi.dk"
API_KEY_HEADER = "X-Api-Key"
REQUEST_TIMEOUT = 20

# Tomorrow's prices are published around 13:00 Danish time, so poll often
# enough to pick them up promptly without hammering the API.
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

CONF_ZONE = "zone"
CONF_OPERATOR = "operator"
CONF_API_KEY = "api_key"

# The API's "today" is the Danish calendar day, so day bucketing and the
# request window follow Copenhagen time rather than the Home Assistant
# instance's configured timezone. A user may run HA in any timezone; that
# should not shift which prices count as "today".
DANISH_TZ = "Europe/Copenhagen"

ZONES = ["dk1", "dk2"]
DEFAULT_ZONE = "dk1"

MANUFACTURER = "data.elprisapi.dk"
