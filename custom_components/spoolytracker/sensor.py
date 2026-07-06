"""Capteurs SpoolyTracker (V1, volontairement minimal)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SpoolyTrackerCoordinator
from .entity import SpoolyTrackerEntity
from .models import SpoolyTrackerData


@dataclass(frozen=True, kw_only=True)
class SpoolyTrackerSensorDescription(SensorEntityDescription):
    """Description de capteur avec extracteurs de valeur et d'attributs."""

    value_fn: Callable[[SpoolyTrackerData], Any]
    attrs_fn: Callable[[SpoolyTrackerData], dict[str, Any]] | None = None
    available_fn: Callable[[SpoolyTrackerData], bool] | None = None


def _total_remaining(data: SpoolyTrackerData) -> float | None:
    stats = data.stats or {}
    if "totalRemaining" in stats:
        return round(float(stats["totalRemaining"]), 1)
    if not data.spools:
        return None
    return round(sum(s.weight_remaining or 0 for s in data.spools), 1)


def _low_stock_count(data: SpoolyTrackerData) -> int:
    stats = data.stats or {}
    if "lowStockCount" in stats:
        return int(stats["lowStockCount"])
    return sum(1 for s in data.spools if s.is_low_stock)


SENSORS: tuple[SpoolyTrackerSensorDescription, ...] = (
    SpoolyTrackerSensorDescription(
        key="total_spools",
        translation_key="total_spools",
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.stats or {}).get("spoolCount", len(d.spools)),
    ),
    SpoolyTrackerSensorDescription(
        key="low_stock_spools",
        translation_key="low_stock_spools",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_low_stock_count,
        attrs_fn=lambda d: {
            "spools": [s.label for s in d.spools if s.is_low_stock][:50]
        },
    ),
    SpoolyTrackerSensorDescription(
        key="total_remaining_weight",
        translation_key="total_remaining_weight",
        icon="mdi:weight-gram",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_total_remaining,
    ),
    SpoolyTrackerSensorDescription(
        key="last_consumption",
        translation_key="last_consumption",
        icon="mdi:printer-3d-nozzle",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        value_fn=lambda d: (d.last_consumption or {}).get("grams_used"),
        attrs_fn=lambda d: d.last_consumption or {},
    ),
    SpoolyTrackerSensorDescription(
        key="api_status",
        translation_key="api_status",
        icon="mdi:cloud-check-variant",
        value_fn=lambda d: "ok",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SpoolyTrackerCoordinator = entry.runtime_data
    async_add_entities(
        SpoolyTrackerSensor(coordinator, description) for description in SENSORS
    )


class SpoolyTrackerSensor(SpoolyTrackerEntity, SensorEntity):
    """Capteur générique piloté par une description."""

    entity_description: SpoolyTrackerSensorDescription

    def __init__(
        self,
        coordinator: SpoolyTrackerCoordinator,
        description: SpoolyTrackerSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if self.entity_description.key == "api_status":
            return "ok" if self.coordinator.last_update_success else "unavailable"
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.data or not self.entity_description.attrs_fn:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        # api_status doit rester disponible même quand l'API est down (il porte l'info).
        if self.entity_description.key == "api_status":
            return True
        return super().available
