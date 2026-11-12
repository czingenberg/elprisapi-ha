"""Constants for the Elpris API integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "elprisapi"
NAME = "Elpris API"
VERSION = "0.1.0"

API_BASE = "https://data.elprisapi.dk"
API_KEY_HEADER = "X-Api-Key"
REQUEST_TIMEOUT = 20

# Tomorrow's prices are published around 13:00 Danish time, so poll often
# enough to pick them up promptly without hammering the API.
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

CONF_ZONE = "zone"
CONF_OPERATOR = "operator"
CONF_API_KEY = "api_key"

ZONES = ["dk1", "dk2"]
DEFAULT_ZONE = "dk1"

MANUFACTURER = "data.elprisapi.dk"
