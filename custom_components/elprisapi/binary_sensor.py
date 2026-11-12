"""Binary sensor platform for the Elpris API integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, VERSION
from .coordinator import ElprisApiCoordinator

TOMORROW_AVAILABLE = BinarySensorEntityDescription(
    key="tomorrow_prices_available",
    translation_key="tomorrow_prices_available",
    name="Tomorrow prices available",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    icon="mdi:calendar-check",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elpris API binary sensor from a config entry."""
    coordinator: ElprisApiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ElprisApiTomorrowAvailable(coordinator)])


class ElprisApiTomorrowAvailable(
    CoordinatorEntity[ElprisApiCoordinator], BinarySensorEntity
):
    """Whether tomorrow's prices have been published yet.

    The API publishes tomorrow's prices around 13:00 Danish time. Useful as an
    automation condition before re-planning tomorrow's charging.
    """

    _attr_has_entity_name = True
    entity_description = TOMORROW_AVAILABLE

    def __init__(self, coordinator: ElprisApiCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        slug = f"{coordinator.zone}_{coordinator.operator or 'none'}"
        self._attr_unique_id = f"{slug}_{TOMORROW_AVAILABLE.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, slug)},
            "name": f"Elpris API {coordinator.zone.upper()}",
            "manufacturer": MANUFACTURER,
            "model": f"Elpris API · {coordinator.zone.upper()}"
            + (f" · {coordinator.operator}" if coordinator.operator else ""),
            "sw_version": VERSION,
            "configuration_url": "https://data.elprisapi.dk/docs/",
        }

    @property
    def is_on(self) -> bool:
        """Return True once tomorrow's prices are available."""
        return bool(self.coordinator.data and self.coordinator.data.tomorrow_available)
