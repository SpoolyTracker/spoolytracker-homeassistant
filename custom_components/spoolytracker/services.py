"""Services Home Assistant exposés par SpoolyTracker.

Services génériques, pilotables par n'importe quelle automatisation / script /
intégration. AUCUNE dépendance à Bambu Lab ou à une imprimante particulière.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import (
    SpoolyTrackerAuthError,
    SpoolyTrackerConnectionError,
    SpoolyTrackerError,
)
from .const import (
    ATTR_ALLOW_AMBIGUOUS,
    ATTR_AMS_SLOT,
    ATTR_AMS_UNIT,
    ATTR_BRAND,
    ATTR_COLOR,
    ATTR_EXTERNAL,
    ATTR_FILAMENT_PROFILE,
    ATTR_GRAMS_USED,
    ATTR_JOB_NAME,
    ATTR_LENGTH_USED_M,
    ATTR_MATERIAL,
    ATTR_METADATA,
    ATTR_PRINTER_NAME,
    ATTR_PROJECT_ID,
    ATTR_SOURCE,
    ATTR_SPOOL_ID,
    DEFAULT_ALLOW_AMBIGUOUS,
    DEFAULT_SOURCE,
    DOMAIN,
    EVENT_CONSUMPTION_LOGGED,
    EVENT_CONSUMPTION_UNRESOLVED,
    OPT_SLOT_MAP,
    OPT_STRATEGY_METADATA,
    OPT_STRATEGY_SELECT,
    OPT_STRATEGY_SLOT,
    SERVICE_CLEAR_SLOT_SPOOL,
    SERVICE_LOG_CONSUMPTION,
    SERVICE_REFRESH,
    SERVICE_SET_SLOT_SPOOL,
)
from .coordinator import SpoolyTrackerCoordinator
from .matching import MatchStatus, SpoolResolver, slot_key

_LOGGER = logging.getLogger(__name__)

# --- Schémas de service --------------------------------------------------------

LOG_CONSUMPTION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_SPOOL_ID): vol.Any(cv.string, cv.positive_int),
        vol.Required(ATTR_GRAMS_USED): vol.Coerce(float),
        vol.Optional(ATTR_LENGTH_USED_M): vol.Coerce(float),
        vol.Optional(ATTR_PRINTER_NAME): cv.string,
        vol.Optional(ATTR_JOB_NAME): cv.string,
        vol.Optional(ATTR_PROJECT_ID): cv.string,
        vol.Optional(ATTR_SOURCE, default=DEFAULT_SOURCE): cv.string,
        vol.Optional(ATTR_METADATA): dict,
        vol.Optional(ATTR_AMS_UNIT): vol.Coerce(int),
        vol.Optional(ATTR_AMS_SLOT): vol.Coerce(int),
        vol.Optional(ATTR_EXTERNAL): cv.boolean,
        vol.Optional(ATTR_MATERIAL): cv.string,
        vol.Optional(ATTR_COLOR): cv.string,
        vol.Optional(ATTR_BRAND): cv.string,
        vol.Optional(ATTR_FILAMENT_PROFILE): cv.string,
        vol.Optional(
            ATTR_ALLOW_AMBIGUOUS, default=DEFAULT_ALLOW_AMBIGUOUS
        ): cv.boolean,
    }
)

_SLOT_TARGET = {
    vol.Required(ATTR_PRINTER_NAME): cv.string,
    vol.Optional(ATTR_AMS_UNIT): vol.Coerce(int),
    vol.Optional(ATTR_AMS_SLOT): vol.Coerce(int),
    vol.Optional(ATTR_EXTERNAL): cv.boolean,
}

SET_SLOT_SPOOL_SCHEMA = vol.Schema(
    {**_SLOT_TARGET, vol.Required(ATTR_SPOOL_ID): vol.Any(cv.string, cv.positive_int)}
)
CLEAR_SLOT_SPOOL_SCHEMA = vol.Schema(dict(_SLOT_TARGET))


# --- Utilitaires --------------------------------------------------------------


def _coordinators(hass: HomeAssistant) -> list[SpoolyTrackerCoordinator]:
    coords: list[SpoolyTrackerCoordinator] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, SpoolyTrackerCoordinator):
            coords.append(coordinator)
    return coords


def _pick_coordinator(
    hass: HomeAssistant, spool_id: Any = None
) -> SpoolyTrackerCoordinator:
    """Choisit l'instance cible.

    S'il existe plusieurs instances, on privilégie celle qui contient la bobine
    demandée ; sinon la première chargée.
    """
    coords = _coordinators(hass)
    if not coords:
        raise HomeAssistantError(
            "Aucune instance SpoolyTracker n'est configurée ou chargée."
        )
    if spool_id not in (None, ""):
        for coordinator in coords:
            if coordinator.data and coordinator.data.spool_by_id(spool_id):
                return coordinator
    return coords[0]


def _build_notes(data: dict[str, Any]) -> str:
    """Construit une note lisible agrégeant le contexte HA.

    Ex. : « HA · Bambu P1S · AMS1/slot3 · PETG black (Bambu) · 13.2m · src=... »
    """
    parts: list[str] = ["HA"]
    if data.get(ATTR_PRINTER_NAME):
        parts.append(str(data[ATTR_PRINTER_NAME]))
    if data.get(ATTR_AMS_UNIT) is not None and data.get(ATTR_AMS_SLOT) is not None:
        parts.append(f"AMS{data[ATTR_AMS_UNIT]}/slot{data[ATTR_AMS_SLOT]}")
    elif data.get(ATTR_EXTERNAL):
        parts.append("bobine externe")

    mat_color = " ".join(
        str(x) for x in (data.get(ATTR_MATERIAL), data.get(ATTR_COLOR)) if x
    )
    if mat_color:
        brand = f" ({data[ATTR_BRAND]})" if data.get(ATTR_BRAND) else ""
        parts.append(f"{mat_color}{brand}")
    if data.get(ATTR_FILAMENT_PROFILE):
        parts.append(str(data[ATTR_FILAMENT_PROFILE]))
    if data.get(ATTR_LENGTH_USED_M) is not None:
        parts.append(f"{data[ATTR_LENGTH_USED_M]}m")
    if data.get(ATTR_PROJECT_ID):
        parts.append(f"projet={data[ATTR_PROJECT_ID]}")
    if data.get(ATTR_SOURCE):
        parts.append(f"src={data[ATTR_SOURCE]}")
    return " · ".join(parts)


# --- Implémentations ----------------------------------------------------------


async def _handle_log_consumption(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    data = dict(call.data)
    coordinator = _pick_coordinator(hass, data.get(ATTR_SPOOL_ID))
    opts = coordinator.entry.options

    resolver = SpoolResolver(
        enable_slot=opts.get(OPT_STRATEGY_SLOT, True),
        enable_select=opts.get(OPT_STRATEGY_SELECT, True),
        enable_metadata=opts.get(OPT_STRATEGY_METADATA, True),
    )
    spools = coordinator.data.spools if coordinator.data else []

    result = resolver.resolve(
        data,
        spools,
        slot_map=coordinator.slot_map,
        active_selects=coordinator.active_selects,
        allow_ambiguous=bool(data.get(ATTR_ALLOW_AMBIGUOUS)),
    )

    grams = float(data[ATTR_GRAMS_USED])
    context = {
        "grams_used": grams,
        "printer_name": data.get(ATTR_PRINTER_NAME),
        "job_name": data.get(ATTR_JOB_NAME),
        "source": data.get(ATTR_SOURCE),
        "ams_unit": data.get(ATTR_AMS_UNIT),
        "ams_slot": data.get(ATTR_AMS_SLOT),
        "material": data.get(ATTR_MATERIAL),
        "color": data.get(ATTR_COLOR),
        "brand": data.get(ATTR_BRAND),
        "filament_profile": data.get(ATTR_FILAMENT_PROFILE),
        "length_used_m": data.get(ATTR_LENGTH_USED_M),
        "project_id": data.get(ATTR_PROJECT_ID),
        "strategy": result.strategy,
    }

    # --- S5 : échecs (jamais de log silencieux) -------------------------------
    if result.status is MatchStatus.NOT_FOUND:
        hass.bus.async_fire(
            EVENT_CONSUMPTION_UNRESOLVED,
            {**context, "status": "not_found", "reason": result.reason},
        )
        _LOGGER.warning(
            "Consommation non résolue (aucune bobine) : %s — %s g non enregistrés",
            result.reason,
            grams,
        )
        raise HomeAssistantError(
            f"Aucune bobine identifiée ({result.reason}). "
            "Fournissez spool_id, configurez un mapping de slot, "
            "ou sélectionnez une bobine active."
        )

    if result.status is MatchStatus.AMBIGUOUS:
        labels = ", ".join(s.label for s in result.candidates)
        hass.bus.async_fire(
            EVENT_CONSUMPTION_UNRESOLVED,
            {
                **context,
                "status": "ambiguous",
                "reason": result.reason,
                "candidates": [s.id for s in result.candidates],
            },
        )
        _LOGGER.warning("Consommation ambiguë : %s (%s)", result.reason, labels)
        raise HomeAssistantError(
            f"Plusieurs bobines correspondent ({labels}). "
            "Précisez spool_id ou activez allow_ambiguous_match."
        )

    # --- Résolu : on envoie -----------------------------------------------------
    spool = result.spool
    assert spool is not None
    notes = _build_notes(data)

    try:
        api_response = await coordinator.client.log_consumption(
            spool.id,
            grams,
            notes=notes,
            external_job_id=data.get(ATTR_JOB_NAME),
            consumption_type="PRINT",
        )
    except SpoolyTrackerAuthError as err:
        raise HomeAssistantError(
            "Token SpoolyTracker refusé — reconfigurez l'intégration."
        ) from err
    except SpoolyTrackerConnectionError as err:
        raise HomeAssistantError(f"SpoolyTracker injoignable : {err}") from err
    except SpoolyTrackerError as err:
        raise HomeAssistantError(f"Échec de l'enregistrement : {err}") from err

    logged = {
        **context,
        "spool_id": spool.id,
        "spool_label": spool.label,
        "notes": notes,
        "status": "logged",
    }
    coordinator.note_last_consumption(logged)
    hass.bus.async_fire(EVENT_CONSUMPTION_LOGGED, logged)
    _LOGGER.info(
        "Consommation enregistrée : %s g sur %s (stratégie=%s)",
        grams,
        spool.label,
        result.strategy,
    )

    # Rafraîchit pour refléter le nouveau poids restant.
    await coordinator.async_request_refresh()

    return {
        "spool_id": spool.id,
        "spool_label": spool.label,
        "grams_used": grams,
        "strategy": result.strategy,
        "api_response": api_response,
    }


async def _handle_set_slot_spool(hass: HomeAssistant, call: ServiceCall) -> None:
    data = call.data
    coordinator = _pick_coordinator(hass, data.get(ATTR_SPOOL_ID))
    key = slot_key(
        data[ATTR_PRINTER_NAME],
        data.get(ATTR_AMS_UNIT),
        data.get(ATTR_AMS_SLOT),
        bool(data.get(ATTR_EXTERNAL)),
    )
    slot_map = dict(coordinator.entry.options.get(OPT_SLOT_MAP, {}))
    slot_map[key] = str(data[ATTR_SPOOL_ID])
    hass.config_entries.async_update_entry(
        coordinator.entry,
        options={**coordinator.entry.options, OPT_SLOT_MAP: slot_map},
    )
    _LOGGER.info("Slot mappé : %s -> bobine %s", key, data[ATTR_SPOOL_ID])


async def _handle_clear_slot_spool(hass: HomeAssistant, call: ServiceCall) -> None:
    data = call.data
    coordinator = _pick_coordinator(hass)
    key = slot_key(
        data[ATTR_PRINTER_NAME],
        data.get(ATTR_AMS_UNIT),
        data.get(ATTR_AMS_SLOT),
        bool(data.get(ATTR_EXTERNAL)),
    )
    slot_map = dict(coordinator.entry.options.get(OPT_SLOT_MAP, {}))
    if key not in slot_map:
        raise ServiceValidationError(f"Aucun mapping pour le slot « {key} ».")
    slot_map.pop(key)
    hass.config_entries.async_update_entry(
        coordinator.entry,
        options={**coordinator.entry.options, OPT_SLOT_MAP: slot_map},
    )
    _LOGGER.info("Mapping de slot supprimé : %s", key)


async def _handle_refresh(hass: HomeAssistant, call: ServiceCall) -> None:
    coords = _coordinators(hass)
    if not coords:
        raise HomeAssistantError("Aucune instance SpoolyTracker chargée.")
    for coordinator in coords:
        await coordinator.async_request_refresh()


# --- Enregistrement -----------------------------------------------------------


def async_setup_services(hass: HomeAssistant) -> None:
    """Enregistre les services une seule fois (partagés entre instances)."""
    if hass.services.has_service(DOMAIN, SERVICE_LOG_CONSUMPTION):
        return

    async def log_consumption(call: ServiceCall) -> ServiceResponse:
        return await _handle_log_consumption(hass, call)

    async def set_slot_spool(call: ServiceCall) -> None:
        await _handle_set_slot_spool(hass, call)

    async def clear_slot_spool(call: ServiceCall) -> None:
        await _handle_clear_slot_spool(hass, call)

    async def refresh(call: ServiceCall) -> None:
        await _handle_refresh(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_CONSUMPTION,
        log_consumption,
        schema=LOG_CONSUMPTION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SLOT_SPOOL, set_slot_spool, schema=SET_SLOT_SPOOL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_SLOT_SPOOL,
        clear_slot_spool,
        schema=CLEAR_SLOT_SPOOL_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh)


def async_unload_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_LOG_CONSUMPTION,
        SERVICE_SET_SLOT_SPOOL,
        SERVICE_CLEAR_SLOT_SPOOL,
        SERVICE_REFRESH,
    ):
        hass.services.async_remove(DOMAIN, service)
