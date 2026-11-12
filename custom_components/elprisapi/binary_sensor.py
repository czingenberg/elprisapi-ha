"""Binary sensor platform for the Elpris API integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ElprisApiConfigEntry, ElprisApiCoordinator
from .entity import ElprisApiEntity

TOMORROW_AVAILABLE = BinarySensorEntityDescription(
    key="tomorrow_prices_available",
    translation_key="tomorrow_prices_available",
    icon="mdi:calendar-check",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ElprisApiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elpris API binary sensor from a config entry."""
    async_add_entities([ElprisApiTomorrowAvailable(entry.runtime_data)])


class ElprisApiTomorrowAvailable(ElprisApiEntity, BinarySensorEntity):
    """Whether tomorrow's prices have been published yet.

    The API publishes tomorrow's prices around 13:00 Danish time. Useful as an
    automation condition before re-planning tomorrow's charging.
    """

    entity_description = TOMORROW_AVAILABLE

    def __init__(self, coordinator: ElprisApiCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, TOMORROW_AVAILABLE.key)

    @property
    def is_on(self) -> bool:
        """Return True once tomorrow's prices are available."""
        return bool(self.coordinator.data and self.coordinator.data.tomorrow_available)
