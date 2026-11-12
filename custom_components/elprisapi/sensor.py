"""Sensor platform for the Elpris API integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, VERSION
from .coordinator import ElprisApiCoordinator, ElprisApiData
from .pricing import COMPONENTS, forecast_attribute

# Home Assistant has no currency constant for DKK, so it is passed as a literal.
CURRENCY_DKK = "DKK"


def _attr(document: dict[str, Any] | None, key: str) -> float | None:
    """Read one price component from a slot breakdown."""
    if not document:
        return None
    return document.get(key)


@dataclass(frozen=True, kw_only=True)
class ElprisApiSensorEntityDescription(SensorEntityDescription):
    """Describes an Elpris API sensor and how to read its value."""

    value_fn: Callable[[ElprisApiData], float | None]
    extra_fn: Callable[[ElprisApiData], dict[str, Any]] | None = None
    component: str | None = None


def _component(component: str) -> Callable[[ElprisApiData], float | None]:
    def _read(data: ElprisApiData) -> float | None:
        return _attr(data.current_breakdown, component)

    return _read


def _today_stat(stat: str) -> Callable[[ElprisApiData], float | None]:
    def _read(data: ElprisApiData) -> float | None:
        return (data.today_stats or {}).get(stat)

    return _read


def _tomorrow_stat(stat: str) -> Callable[[ElprisApiData], float | None]:
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


SENSORS: tuple[ElprisApiSensorEntityDescription, ...] = (
    ElprisApiSensorEntityDescription(
        key="current_price",
        translation_key="current_price",
        name="Current price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("total"),
        extra_fn=_forecast,
        icon="mdi:flash",
    ),
    ElprisApiSensorEntityDescription(
        key="current_price_excl_vat",
        translation_key="current_price_excl_vat",
        name="Current price excl. VAT",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("total_excl_vat"),
        icon="mdi:flash-outline",
    ),
    ElprisApiSensorEntityDescription(
        key="spot_price",
        translation_key="spot_price",
        name="Spot price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("spot_price"),
        icon="mdi:chart-line",
    ),
    ElprisApiSensorEntityDescription(
        key="electricity_tax",
        translation_key="electricity_tax",
        name="Electricity tax",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("electricity_tax"),
        icon="mdi:cash",
    ),
    ElprisApiSensorEntityDescription(
        key="system_tariff",
        translation_key="system_tariff",
        name="System tariff",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("system_tariff"),
        icon="mdi:transmission-tower",
    ),
    ElprisApiSensorEntityDescription(
        key="transmission_tariff",
        translation_key="transmission_tariff",
        name="Transmission tariff",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("transmission_tariff"),
        icon="mdi:transmission-tower-export",
    ),
    ElprisApiSensorEntityDescription(
        key="grid_tariff",
        translation_key="grid_tariff",
        name="Grid tariff",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("grid_tariff"),
        icon="mdi:transmission-tower-import",
    ),
    ElprisApiSensorEntityDescription(
        key="vat",
        translation_key="vat",
        name="VAT",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        value_fn=_component("vat"),
        icon="mdi:percent",
    ),
    ElprisApiSensorEntityDescription(
        key="today_min",
        translation_key="today_min",
        name="Today min price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_today_stat("min"),
        icon="mdi:arrow-down",
    ),
    ElprisApiSensorEntityDescription(
        key="today_mean",
        translation_key="today_mean",
        name="Today mean price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=4,
        value_fn=_today_stat("mean"),
        icon="mdi:approximately-equal",
    ),
    ElprisApiSensorEntityDescription(
        key="today_max",
        translation_key="today_max",
        name="Today max price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_today_stat("max"),
        icon="mdi:arrow-up",
    ),
    ElprisApiSensorEntityDescription(
        key="tomorrow_min",
        translation_key="tomorrow_min",
        name="Tomorrow min price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_tomorrow_stat("min"),
        icon="mdi:arrow-down",
    ),
    ElprisApiSensorEntityDescription(
        key="tomorrow_mean",
        translation_key="tomorrow_mean",
        name="Tomorrow mean price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=4,
        value_fn=_tomorrow_stat("mean"),
        icon="mdi:approximately-equal",
    ),
    ElprisApiSensorEntityDescription(
        key="tomorrow_max",
        translation_key="tomorrow_max",
        name="Tomorrow max price",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_tomorrow_stat("max"),
        icon="mdi:arrow-up",
    ),
    ElprisApiSensorEntityDescription(
        key="today_forecast",
        translation_key="today_forecast",
        name="Today prices",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: _today_stat("mean")(data),
        extra_fn=_today_forecast,
        icon="mdi:calendar-today",
    ),
    ElprisApiSensorEntityDescription(
        key="tomorrow_forecast",
        translation_key="tomorrow_forecast",
        name="Tomorrow prices",
        native_unit_of_measurement=f"{CURRENCY_DKK}/{UnitOfEnergy.KILO_WATT_HOUR}",
        value_fn=lambda data: _tomorrow_stat("mean")(data),
        extra_fn=_tomorrow_forecast,
        icon="mdi:calendar-arrow-right",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Elpris API sensors from a config entry."""
    coordinator: ElprisApiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ElprisApiSensor(coordinator, description) for description in SENSORS
    )


class ElprisApiSensor(CoordinatorEntity[ElprisApiCoordinator], SensorEntity):
    """A price component or daily statistic from Elpris API."""

    _attr_has_entity_name = True
    entity_description: ElprisApiSensorEntityDescription

    def __init__(
        self,
        coordinator: ElprisApiCoordinator,
        description: ElprisApiSensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.zone}_{coordinator.operator or 'none'}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.zone}_{coordinator.operator or 'none'}")},
            "name": f"Elpris API {coordinator.zone.upper()}",
            "manufacturer": MANUFACTURER,
            "model": f"Elpris API · {coordinator.zone.upper()}"
            + (f" · {coordinator.operator}" if coordinator.operator else ""),
            "sw_version": VERSION,
            "configuration_url": "https://data.elprisapi.dk/docs/",
        }

    @property
    def native_value(self) -> float | None:
        """Return the sensor value, or None while prices are unavailable."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the hourly forecast on the sensors that carry it."""
        if self.coordinator.data is None or self.entity_description.extra_fn is None:
            return None
        return self.entity_description.extra_fn(self.coordinator.data)
