"""Constantes de l'intégration SpoolyTracker.

Toutes les URL de l'API SpoolyTracker sont centralisées ici : c'est le SEUL
endroit où elles doivent apparaître. `api.py` construit ses chemins à partir de
ces constantes, ce qui rend l'adaptation à une future version de l'API triviale.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "spoolytracker"

# --- Métadonnées d'intégration -------------------------------------------------
MANUFACTURER: Final = "SpoolyTracker"
DEFAULT_NAME: Final = "SpoolyTracker"

# --- Endpoints de l'API publique ----------------------------------------------
# Base : <base_url>/public-api/v1
# Auth : header "Authorization: Bearer <token>" (l'API accepte aussi x-api-key).
API_BASE_PATH: Final = "/public-api/v1"

# Ressources (relatives à API_BASE_PATH).
EP_FILAMENTS: Final = "/filaments"                 # GET  -> liste des bobines
EP_FILAMENT: Final = "/filaments/{spool_id}"       # GET  -> une bobine
EP_FILAMENT_STOCK: Final = "/filaments/{spool_id}/stock"  # PATCH {weightRemaining}
EP_CONSUMPTION: Final = "/consumption"             # GET / POST
EP_ANALYTICS_STOCK: Final = "/analytics/stock"     # GET  -> stats de stock
EP_ANALYTICS_CONSUMPTION: Final = "/analytics/consumption"  # GET -> agrégats

# TODO(API SpoolyTracker) : endpoint projets non exposé publiquement pour l'instant.
# Le scope "projects:read" existe mais aucun controller ne le sert.
# Quand il existera, décommenter et implémenter get_projects() dans api.py.
EP_PROJECTS: Final = "/projects"  # (non disponible pour l'instant)

# --- Clés de config_entry (data) ----------------------------------------------
CONF_BASE_URL: Final = "base_url"
CONF_API_TOKEN: Final = "api_token"
CONF_NAME: Final = "name"

# --- Clés d'options ------------------------------------------------------------
OPT_SCAN_INTERVAL: Final = "scan_interval"
OPT_SLOT_MAP: Final = "slot_map"
OPT_STRATEGY_DIRECT: Final = "strategy_direct"       # S1 (toujours implicite ON)
OPT_STRATEGY_SLOT: Final = "strategy_slot"           # S2
OPT_STRATEGY_SELECT: Final = "strategy_select"       # S4
OPT_STRATEGY_METADATA: Final = "strategy_metadata"   # S3
OPT_ALLOW_AMBIGUOUS: Final = "allow_ambiguous_match"

# Valeurs par défaut.
DEFAULT_SCAN_INTERVAL: Final = 300  # secondes
DEFAULT_STRATEGY_SLOT: Final = True
DEFAULT_STRATEGY_SELECT: Final = True
DEFAULT_STRATEGY_METADATA: Final = True
DEFAULT_ALLOW_AMBIGUOUS: Final = False

# --- Réseau --------------------------------------------------------------------
DEFAULT_TIMEOUT: Final = 20  # secondes

# --- Événements Home Assistant -------------------------------------------------
EVENT_CONSUMPTION_LOGGED: Final = "spoolytracker_consumption_logged"
EVENT_CONSUMPTION_UNRESOLVED: Final = "spoolytracker_consumption_unresolved"

# --- Services ------------------------------------------------------------------
SERVICE_LOG_CONSUMPTION: Final = "log_consumption"
SERVICE_SET_SLOT_SPOOL: Final = "set_slot_spool"
SERVICE_CLEAR_SLOT_SPOOL: Final = "clear_slot_spool"
SERVICE_REFRESH: Final = "refresh"

# --- Champs de service ---------------------------------------------------------
ATTR_SPOOL_ID: Final = "spool_id"
ATTR_GRAMS_USED: Final = "grams_used"
ATTR_LENGTH_USED_M: Final = "length_used_m"
ATTR_PRINTER_NAME: Final = "printer_name"
ATTR_JOB_NAME: Final = "job_name"
ATTR_PROJECT_ID: Final = "project_id"
ATTR_SOURCE: Final = "source"
ATTR_METADATA: Final = "metadata"
ATTR_AMS_UNIT: Final = "ams_unit"
ATTR_AMS_SLOT: Final = "ams_slot"
ATTR_EXTERNAL: Final = "external"
ATTR_MATERIAL: Final = "material"
ATTR_COLOR: Final = "color"
ATTR_BRAND: Final = "brand"
ATTR_FILAMENT_PROFILE: Final = "filament_profile"
ATTR_ALLOW_AMBIGUOUS: Final = "allow_ambiguous_match"

DEFAULT_SOURCE: Final = "home_assistant"

# Valeur d'option d'un select signifiant « aucune bobine active ».
SELECT_NONE: Final = "none"
