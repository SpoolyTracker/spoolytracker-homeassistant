"""Intégration SpoolyTracker pour Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SpoolyTrackerApiClient
from .const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPT_SCAN_INTERVAL,
)
from .coordinator import SpoolyTrackerCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]

type SpoolyTrackerConfigEntry = ConfigEntry[SpoolyTrackerCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: SpoolyTrackerConfigEntry
) -> bool:
    """Configure une instance SpoolyTracker."""
    session = async_get_clientsession(hass)
    client = SpoolyTrackerApiClient(
        base_url=entry.data[CONF_BASE_URL],
        token=entry.data[CONF_API_TOKEN],
        session=session,
    )

    scan_interval = entry.options.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SpoolyTrackerCoordinator(hass, entry, client, scan_interval)

    # Premier rafraîchissement : lève ConfigEntryAuthFailed/UpdateFailed si besoin.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Les services sont partagés entre toutes les entrées : enregistrés une fois.
    async_setup_services(hass)

    # Recharge l'entrée quand les options changent (intervalle, stratégies…).
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("Intégration SpoolyTracker configurée (%s)", entry.title)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SpoolyTrackerConfigEntry
) -> bool:
    """Décharge une instance SpoolyTracker."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Retire les services quand plus aucune entrée n'est chargée.
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state.recoverable
    ]
    if not remaining:
        async_unload_services(hass)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: SpoolyTrackerConfigEntry
) -> None:
    """Recharge l'entrée après modification des options."""
    await hass.config_entries.async_reload(entry.entry_id)
