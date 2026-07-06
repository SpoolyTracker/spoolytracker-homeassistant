"""DataUpdateCoordinator SpoolyTracker : bobines + statistiques de stock."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SpoolyTrackerApiClient,
    SpoolyTrackerAuthError,
    SpoolyTrackerConnectionError,
    SpoolyTrackerError,
)
from .const import DOMAIN
from .models import Spool, SpoolyTrackerData

_LOGGER = logging.getLogger(__name__)


class SpoolyTrackerCoordinator(DataUpdateCoordinator[SpoolyTrackerData]):
    """Récupère et met en cache l'état SpoolyTracker pour toutes les entités."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SpoolyTrackerApiClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.client = client
        # Conserve la dernière consommation loguée depuis HA (pour le sensor).
        self._last_consumption: dict[str, Any] | None = None
        # Bobine active sélectionnée par slot (clé slot -> spool_id) + "__global__".
        # Renseigné par les entités select ; lu par le résolveur (stratégie S4).
        self.active_selects: dict[str, str] = {}

    @property
    def slot_map(self) -> dict[str, Any]:
        """Mapping slot -> spool_id, persisté dans les options de l'entrée."""
        from .const import OPT_SLOT_MAP

        return dict(self.entry.options.get(OPT_SLOT_MAP, {}))

    def note_last_consumption(self, payload: dict[str, Any]) -> None:
        """Mémorise la dernière consommation loguée via HA."""
        self._last_consumption = payload

    async def _async_update_data(self) -> SpoolyTrackerData:
        try:
            spools_raw = await self.client.get_spools()
            stats = await self.client.get_stats()
        except SpoolyTrackerAuthError as err:
            # Déclenche le flux de réauthentification.
            raise ConfigEntryAuthFailed(str(err)) from err
        except SpoolyTrackerConnectionError as err:
            raise UpdateFailed(f"SpoolyTracker injoignable : {err}") from err
        except SpoolyTrackerError as err:
            raise UpdateFailed(f"Erreur API SpoolyTracker : {err}") from err

        spools = [Spool.from_api(item) for item in spools_raw]
        return SpoolyTrackerData(
            spools=spools,
            stats=stats,
            last_consumption=self._last_consumption,
        )
