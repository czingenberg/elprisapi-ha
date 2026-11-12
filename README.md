# Elpris API for Home Assistant

Custom integration for [data.elprisapi.dk](https://data.elprisapi.dk/docs/) — Danish
hourly electricity prices (DK1/DK2) with the **full tariff breakdown**: spot price,
electricity tax, system tariff, transmission tariff, grid operator tariff, and VAT.

## What it gives you

One sensor per price component, so the breakdown is available to templates,
statistics and dashboards without parsing an attribute dict:

- **Spot price** — the hourly market spot price for your price area
- **Electricity tax** (elafgift)
- **System tariff** (systemtarif)
- **Transmission tariff** (transmissionsnettarif)
- **Grid tariff** (nettarif) — your grid operator's charge, which varies by hour
- **VAT** (moms), and the total both with and without it

The grid tariff is included for all 33 Danish operators, resolved per hour from the
operator's own charge codes, so the total reflects what you are billed rather than
the spot price plus a flat guess.

Prices are hourly and cover today and tomorrow, so tomorrow's prices are available
as soon as they are published (around 13:00) — enough to plan EV charging or
appliance runs for the next day.

## Entities

One device per zone/operator pair, named `Elpris API <ZONE> <operator>`. Entity IDs
are prefixed with that name, e.g. `sensor.elpris_api_dk1_n1_current_price`. The
entities are:

| Entity | Description |
| --- | --- |
| `sensor.current_price` | Total price incl. VAT, DKK/kWh. Carries the hourly forecast. |
| `sensor.current_price_excl_vat` | Total price excl. VAT |
| `sensor.spot_price` | Spot price component |
| `sensor.electricity_tax` | Electricity tax (elafgift) |
| `sensor.system_tariff` | System tariff (systemtarif) |
| `sensor.transmission_tariff` | Transmission grid tariff |
| `sensor.grid_tariff` | Your grid operator's hourly tariff |
| `sensor.vat` | VAT component |
| `sensor.today_min` / `today_mean` / `today_max` | Today's total price statistics |
| `sensor.tomorrow_min` / `tomorrow_mean` / `tomorrow_max` | Tomorrow's statistics |
| `sensor.today_prices` / `sensor.tomorrow_prices` | Forecast lists |
| `binary_sensor.tomorrow_prices_available` | On once tomorrow's prices are published (~13:00) |

Prices are in **DKK per kWh**. The API also serves øre; this integration requests DKK,
which the Energy dashboard accepts for a price entity since it validates the
`/kWh` suffix rather than the currency.

The live price sensors use `state_class: measurement`, so long-term statistics keep
their min/mean/max. They change at the start of each hour, when the price changes,
independent of when the API was last polled.

### Forecast format

The forecasts are plain `prices` lists:

```yaml
prices:
  - price: 1.855
    start: "2026-11-12T13:00:00+01:00"
    end: "2026-11-12T14:00:00+01:00"
```

`current_price.prices` holds **today and tomorrow** (up to 48 entries). The per-day
sensors hold their own day only.

That shape means `ev_smart_charging` can use `sensor.current_price` as its price
sensor directly — it accepts a `prices` attribute with `price` and `start` keys at
hourly intervals, which is what this exposes. No template sensor needed.

The `prices` attribute is excluded from the recorder, so it does not grow the
database with a copy on every state change.

## Installation

### HACS (custom repository)

1. HACS → **⋮** → **Custom repositories**
2. Add `https://github.com/czingenberg/elprisapi-ha`, category **Integration**
3. Install **Elpris API**, then restart Home Assistant

### Manual

Copy `custom_components/elprisapi/` into your Home Assistant
`config/custom_components/` directory and restart.

## Getting an API key

The key is **free**. Request one at
**[elprisapi.dk/#api-noegle](https://elprisapi.dk/#api-noegle)** — enter your email
and it is delivered by mail (no account, no spam).

## Configuration

**Settings → Devices & Services → Add Integration → Elpris API**

The setup has two steps:

| Step | Field | Notes |
| --- | --- | --- |
| 1 | API key | Free from [elprisapi.dk/#api-noegle](https://elprisapi.dk/#api-noegle). Sent as `X-Api-Key`. |
| 1 | Price zone | `dk1` (west of the Great Belt) or `dk2` (east). |
| 2 | Grid operator | Picked from the API's own list. Adds the grid tariff. Choose **No grid operator** for prices without it. |

Your zone is determined by where you live relative to the Great Belt, not by your
operator. If the total price looks too low, the grid operator is probably missing.

If the API later rejects the key, Home Assistant asks for a new one
(**Settings → Devices & Services → Elpris API → Reconfigure/Re-authenticate**); there
is no need to remove the integration.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt

.venv/bin/python -m pytest tests/ -q      # full test suite, no network
.venv/bin/python tests/live_check.py      # live API smoke test
```

The test suite needs Python 3.13 or newer, because it runs against a real Home
Assistant install (`pytest-homeassistant-custom-component`).

`tests/live_check.py` reads the key from `$ELPRIS_API_KEY` or `~/elapi`, and asserts
that the price components sum to the total, that VAT reconciles at 25%, and that the
date-range request the integration uses matches the single-day requests.

`pricing.py` intentionally has no Home Assistant imports so it can be tested without
a Home Assistant install.

## Notes

- Prices only change once a day, so the API is polled hourly. From 12:00 Danish time
  until tomorrow's prices have arrived (around 13:00) it is polled every 10 minutes.
  Until then the tomorrow statistics are `unknown` and the binary sensor is off.
- Today and tomorrow are fetched in a single date-range request and cached. If the
  API is briefly unreachable, the sensors keep working from the cached prices for as
  long as those cover the current time.
- Daylight saving switch days return 23 or 25 hourly entries. The two 02:00 entries are
  distinguished by their UTC offset and both are kept.

### Upgrading from 0.1.x

- The price sensors are now plain measurements in DKK/kWh instead of "monetary
  totals". Home Assistant may flag their old long-term statistics under
  **Developer tools → Statistics**; choose to delete the old statistics there.
- The device is renamed to include the grid operator. Existing entity IDs are kept;
  only newly added entries get the operator in their entity IDs.

## Licence

[MIT](LICENSE)
