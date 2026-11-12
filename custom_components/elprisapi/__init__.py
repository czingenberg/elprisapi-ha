"""The Elpris API integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_utc_time_change

from .const import CLOCK_TICK_MINUTES
from .coordinator import ElprisApiConfigEntry, ElprisApiCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ElprisApiConfigEntry) -> bool:
    """Set up Elpris API from a config entry."""
    coordinator = ElprisApiCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(
        async_track_utc_time_change(
            hass,
            coordinator.async_handle_clock_tick,
            minute=CLOCK_TICK_MINUTES,
            second=0,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ElprisApiConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
