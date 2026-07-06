"""Diagnostics SpoolyTracker (données sensibles masquées)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_TOKEN, OPT_SLOT_MAP
from .coordinator import SpoolyTrackerCoordinator

TO_REDACT = {CONF_API_TOKEN, "api_token", "token", "authorization"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: SpoolyTrackerCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "spool_count": len(data.spools) if data else 0,
            "stats": data.stats if data else {},
            "slot_map_keys": list(
                entry.options.get(OPT_SLOT_MAP, {}).keys()
            ),
            "last_consumption": data.last_consumption if data else None,
        },
        # Échantillon de bobines sans données personnelles.
        "spools_sample": [
            {
                "id": s.id,
                "brand": s.brand,
                "material": s.material,
                "color_name": s.color_name,
                "weight_remaining": s.weight_remaining,
                "is_low_stock": s.is_low_stock,
            }
            for s in (data.spools[:10] if data else [])
        ],
    }
