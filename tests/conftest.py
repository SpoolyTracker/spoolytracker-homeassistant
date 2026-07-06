"""Configuration pytest : permet d'importer les modules PURS de l'intégration
(`matching`, `models`) sans exiger l'installation de Home Assistant.

On enregistre un paquet « spoolytracker » stub dans sys.modules AVANT toute
importation, pour que `spoolytracker.matching` / `spoolytracker.models` chargent
les fichiers sources directement sans exécuter `__init__.py` (qui, lui, importe
homeassistant).
"""

from __future__ import annotations

import os
import sys
import types

_CUSTOM = os.path.join(os.path.dirname(__file__), "..", "custom_components")
sys.path.insert(0, _CUSTOM)

_pkg_dir = os.path.join(_CUSTOM, "spoolytracker")
if "spoolytracker" not in sys.modules:
    _stub = types.ModuleType("spoolytracker")
    _stub.__path__ = [_pkg_dir]  # type: ignore[attr-defined]
    sys.modules["spoolytracker"] = _stub
