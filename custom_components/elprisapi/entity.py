"""Shared base entity for the Elpris API integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOCS_URL, DOMAIN, MANUFACTURER
from .coordinator import ElprisApiCoordinator


class ElprisApiEntity(CoordinatorEntity[ElprisApiCoordinator]):
    """An entity belonging to one zone/operator pair."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ElprisApiCoordinator, key: str) -> None:
        """Set the unique id and attach the entity to its device."""
        super().__init__(coordinator)
        zone, operator = coordinator.zone, coordinator.operator
        slug = f"{zone}_{operator or 'none'}"
        self._attr_unique_id = f"{slug}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, slug)},
            # The operator is part of the name so that two operators in the
            # same zone do not end up as identically named devices.
            name=f"Elpris API {zone.upper()}" + (f" {operator}" if operator else ""),
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=DOCS_URL,
        )
