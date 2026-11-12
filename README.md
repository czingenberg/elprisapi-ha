# Elpris API for Home Assistant

Custom integration for [data.elprisapi.dk](https://data.elprisapi.dk/docs/) — Danish
hourly electricity prices (DK1/DK2) with the **full tariff breakdown**: spot price,
electricity tax, system tariff, transmission tariff, grid operator tariff, and VAT.

## Why this exists

Home Assistant's built-in `energidataservice` integration gives you spot price plus
system tariffs, but not your **grid operator tariff** (nettarif). That component is
often the largest part of the bill and varies hour by hour. Elpris API resolves it per
operator, so this integration can show a total price that actually reconciles.

## Entities

One device per zone/operator pair, with these entities:

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

Prices are in **DKK per kWh**. The API also serves øre; this integration requests DKK
so values drop straight into the Energy dashboard and `ev_smart_charging`.

### Forecast format

The forecast attributes use the same shape as the `stromligning` integration:

```yaml
prices:
  - price: 1.855
    start: "2026-11-12T13:00:00+01:00"
    end: "2026-11-12T14:00:00+01:00"
```

Dashboards and automations written against `stromligning` work unchanged.

## Installation

### HACS (custom repository)

1. HACS → **⋮** → **Custom repositories**
2. Add `https://github.com/<you>/elprisapi-ha`, category **Integration**
3. Install **Elpris API**, then restart Home Assistant

### Manual

Copy `custom_components/elprisapi/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

**Settings → Devices & Services → Add Integration → Elpris API**

| Field | Notes |
| --- | --- |
| API key | From your elprisapi.dk account. Sent as `X-Api-Key`. |
| Price zone | `dk1` (west of the Great Belt) or `dk2` (east). |
| Grid operator slug | Optional. Adds the grid tariff. Leave empty for prices without it. |

Find your operator slug with:

```sh
curl -H "X-Api-Key: $KEY" https://data.elprisapi.dk/api/v1/operators
```

Common ones: `rah`, `n1`, `radius`, `trefor-el-net`, `konstant`, `cerius`.

Your zone is determined by where you live relative to the Great Belt, not by your
operator. If the total price looks too low, the operator slug is probably missing.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install pytest aiohttp

.venv/bin/python -m pytest tests/ -q      # unit tests, no network
.venv/bin/python tests/live_check.py      # live API smoke test
```

`tests/live_check.py` reads the key from `$ELPRIS_API_KEY` or `~/elapi`, and asserts
that the price components sum to the total and that VAT reconciles at 25%.

`pricing.py` intentionally has no Home Assistant imports so it can be tested without
a Home Assistant install.

## Notes

- Polls every 15 minutes. Tomorrow's prices appear around 13:00 Danish time; until then
  the tomorrow statistics are `unknown` and the binary sensor is off.
- Daylight saving switch days return 23 or 25 hourly entries. The two 02:00 entries are
  distinguished by their UTC offset and both are kept.
- The API allows date ranges up to 31 days; this integration only requests today and
  tomorrow.

## Licence

MIT
