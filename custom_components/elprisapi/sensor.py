"""Sensor platform for the Elpris API integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ElprisApiConfigEntry, ElprisApiCoordinator, ElprisApiData
from .entity import ElprisApiEntity
from .pricing import forecast_attribute

PRICE_UNIT = f"DKK/{UnitOfEnergy.KILO_WATT_HOUR}"

type ValueFn = Callable[[ElprisApiData], float | None]
type ExtraFn = Callable[[ElprisApiData], dict[str, Any]]


@dataclass(frozen=True, kw_only=True)
class ElprisApiSensorEntityDescription(SensorEntityDescription):
    """Describes an Elpris API sensor and how to read its value."""

    value_fn: ValueFn
    extra_fn: ExtraFn | None = None


def _component(component: str) -> ValueFn:
    """Read one price component of the slot covering now."""

    def _read(data: ElprisApiData) -> float | None:
        return (data.current_breakdown or {}).get(component)

    return _read


def _today_stat(stat: str) -> ValueFn:
    def _read(data: ElprisApiData) -> float | None:
        return (data.today_stats or {}).get(stat)

    return _read


def _tomorrow_stat(stat: str) -> ValueFn:
    def _read(data: ElprisApiData) -> float | None:
        return (data.tomorrow_stats or {}).get(stat)

    return _read


def _forecast(data: ElprisApiData) -> dict[str, Any]:
    """Forecast attributes for every slot we hold."""
    return {"prices": forecast_attribute(data.slots)}


def _today_forecast(data: ElprisApiData) -> dict[str, Any]:
    """Forecast attributes limited to today."""
    return {"prices": forecast_attribute(data.today_slots)}


def _tomorrow_forecast(data: ElprisApiData) -> dict[str, Any]:
    """Forecast attributes limited to tomorrow."""
    return {"prices": forecast_attribute(data.tomorrow_slots)}


def _price(
    key: str,
    icon: str,
    value_fn: ValueFn,
    *,
    live: bool = False,
    extra_fn: ExtraFn | None = None,
) -> ElprisApiSensorEntityDescription:
    """Describe a DKK/kWh sensor.

    These are prices per kWh, not amounts of money, so they deliberately have
    no ``monetary`` device class. ``live`` sensors follow the current slot and
    are recorded as measurements so long-term statistics hold min/mean/max.
    """
    return ElprisApiSensorEntityDescription(
        key=key,
        translation_key=key,
        icon=icon,
        native_unit_of_measurement=PRICE_UNIT,
        state_class=SensorStateClass.MEASUREMENT if live else None,
        suggested_display_precision=4,
        value_fn=value_fn,
        extra_fn=extra_fn,
    )


SENSORS: tuple[ElprisApiSensorEntityDescription, ...] = (
    _price(
        "current_price", "mdi:flash", _component("total"), live=True, extra_fn=_forecast
    ),
    _price(
        "current_price_excl_vat",
        "mdi:flash-outline",
        _component("total_excl_vat"),
        live=True,
    ),
    _price("spot_price", "mdi:chart-line", _component("spot_price"), live=True),
    _price("electricity_tax", "mdi:cash", _component("electricity_tax"), live=True),
    _price(
        "system_tariff", "mdi:transmission-tower", _component("system_tariff"), live=True
    ),
    _price(
        "transmission_tariff",
        "mdi:transmission-tower-export",
        _component("transmission_tariff"),
        live=True,
    ),
    _price(
        "grid_tariff",
        "mdi:transmission-tower-import",
        _component("grid_tariff"),
        live=True,
    ),
    _price("vat", "mdi:percent", _component("vat"), live=True),
    _price("today_min", "mdi:arrow-down", _today_stat("min")),
    _price("today_mean", "mdi:approximately-equal", _today_stat("mean")),
    _price("today_max", "mdi:arrow-up", _today_stat("max")),
    _price("tomorrow_min", "mdi:arrow-down", _tomorrow_stat("min")),
    _price("tomorrow_mean", "mdi:approximately-equal", _tomorrow_stat("mean")),
    _price("tomorrow_max", "mdi:arrow-up", _tomorrow_stat("max")),
    _price(
        "today_forecast",
        "mdi:calendar-today",
        _today_stat("mean"),
        extra_fn=_today_forecast,
    ),
    _price(
        "tomorrow_forecast",
        "mdi:calendar-arrow-right",
        _tomorrow_stat("mean"),
        extra_fn=_tomorrow_forecast,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ElprisApiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Elpris API sensors from a config entry."""
    async_add_entities(
        ElprisApiSensor(entry.runtime_data, description) for description in SENSORS
    )


class ElprisApiSensor(ElprisApiEntity, SensorEntity):
    """A price component or daily statistic from Elpris API."""

    entity_description: ElprisApiSensorEntityDescription
    # The forecast list is large and changes daily; keeping it out of the
    # recorder avoids storing a copy with every state change.
    _unrecorded_attributes = frozenset({"prices"})

    def __init__(
        self,
        coordinator: ElprisApiCoordinator,
        description: ElprisApiSensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the sensor value, or None while prices are unavailable."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the forecast on the sensors that carry it."""
        if self.coordinator.data is None or self.entity_description.extra_fn is None:
            return None
        return self.entity_description.extra_fn(self.coordinator.data)
