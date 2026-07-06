"""Entités select SpoolyTracker : bobine active globale + par slot configuré.

Permet la stratégie S4 (sélection active). L'option choisie (un libellé de bobine)
est reprojetée vers l'id de bobine et publiée dans `coordinator.active_selects`,
que le résolveur consulte lors d'un `log_consumption`.
"""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import OPT_SLOT_MAP, SELECT_NONE
from .coordinator import SpoolyTrackerCoordinator
from .entity import SpoolyTrackerEntity

_LOGGER = logging.getLogger(__name__)

GLOBAL_KEY = "__global__"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SpoolyTrackerCoordinator = entry.runtime_data

    entities: list[ActiveSpoolSelect] = [
        ActiveSpoolSelect(coordinator, GLOBAL_KEY, "active_spool")
    ]
    # Un select par slot déjà mappé (créés/retirés au rechargement de l'entrée).
    for slot in entry.options.get(OPT_SLOT_MAP, {}):
        entities.append(ActiveSpoolSelect(coordinator, slot, slot))

    async_add_entities(entities)


class ActiveSpoolSelect(SpoolyTrackerEntity, SelectEntity, RestoreEntity):
    """Select de bobine active pour une clé de slot (ou global)."""

    _attr_icon = "mdi:printer-3d"

    def __init__(
        self,
        coordinator: SpoolyTrackerCoordinator,
        slot_key: str,
        name_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._slot_key = slot_key
        self._selected_spool_id: str | None = None

        safe = slot_key.replace("|", "_").replace("/", "_")
        self._attr_unique_id = f"{coordinator.entry.entry_id}_select_{safe}"
        if slot_key == GLOBAL_KEY:
            self._attr_translation_key = "active_spool"
        else:
            # Nom lisible du slot, ex. « Bambu p1s · ams1/slot3 ».
            pretty = slot_key.replace("|", " · ")
            self._attr_name = f"Bobine active {pretty}"

    # -- Options ----------------------------------------------------------------

    @property
    def options(self) -> list[str]:
        spools = self.coordinator.data.spools if self.coordinator.data else []
        return [SELECT_NONE] + [s.label for s in spools]

    @property
    def current_option(self) -> str:
        if not self._selected_spool_id or not self.coordinator.data:
            return SELECT_NONE
        spool = self.coordinator.data.spool_by_id(self._selected_spool_id)
        return spool.label if spool else SELECT_NONE

    async def async_select_option(self, option: str) -> None:
        if option == SELECT_NONE:
            self._set_selected(None)
        else:
            spools = self.coordinator.data.spools if self.coordinator.data else []
            match = next((s for s in spools if s.label == option), None)
            self._set_selected(str(match.id) if match else None)
        self.async_write_ha_state()

    # -- Publication vers le résolveur -----------------------------------------

    def _set_selected(self, spool_id: str | None) -> None:
        self._selected_spool_id = spool_id
        if spool_id is None:
            self.coordinator.active_selects.pop(self._slot_key, None)
        else:
            self.coordinator.active_selects[self._slot_key] = spool_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restaure la sélection après redémarrage.
        if (last := await self.async_get_last_state()) is not None:
            spool_id = (last.attributes or {}).get("spool_id")
            if spool_id:
                self._set_selected(str(spool_id))

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"spool_id": self._selected_spool_id, "slot_key": self._slot_key}

    @callback
    def _handle_coordinator_update(self) -> None:
        # Réaffirme la sélection dans le dict partagé après chaque refresh.
        if self._selected_spool_id:
            self.coordinator.active_selects[self._slot_key] = self._selected_spool_id
        super()._handle_coordinator_update()
