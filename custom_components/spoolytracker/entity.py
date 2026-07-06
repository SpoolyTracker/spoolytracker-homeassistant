"""Entité de base SpoolyTracker : appareil commun + liaison au coordinator."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SpoolyTrackerCoordinator


class SpoolyTrackerEntity(CoordinatorEntity[SpoolyTrackerCoordinator]):
    """Base commune : toutes les entités appartiennent au même appareil (l'instance)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SpoolyTrackerCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=entry.title,
            configuration_url=entry.data.get("base_url"),
        )
