"""Tests unitaires de la normalisation des données (Spool)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components"))

from spoolytracker.models import Spool  # noqa: E402


def test_from_api_flattens_nested():
    spool = Spool.from_api(
        {
            "id": 7,
            "spoolReference": "REF-7",
            "brand": {"id": 1, "name": "Bambu"},
            "material": {"id": 2, "name": "PETG"},
            "color": "black",
            "colorName": "Noir",
            "weightInitial": 1000,
            "weightRemaining": 250,
            "lowStockThreshold": 300,
            "lowStockThresholdType": "ABSOLUTE",
            "isLocked": False,
        }
    )
    assert spool.id == 7
    assert spool.brand == "Bambu"
    assert spool.material == "PETG"
    assert spool.color_name == "Noir"
    assert "#7" in spool.label and "Bambu" in spool.label
    # Le poids restant apparaît dans le libellé quand il est connu.
    assert "250 g" in spool.label


def test_label_without_weight_has_no_gram_suffix():
    spool = Spool.from_api({"id": 3, "brand": {"name": "Bambu"}})
    assert spool.label.endswith("Bambu")
    assert " g" not in spool.label


def test_from_api_handles_missing_nested():
    spool = Spool.from_api({"id": 9})
    assert spool.brand is None
    assert spool.material is None
    assert spool.label.startswith("#9")


def test_low_stock_absolute():
    spool = Spool.from_api(
        {
            "id": 1,
            "weightInitial": 1000,
            "weightRemaining": 200,
            "lowStockThreshold": 300,
            "lowStockThresholdType": "ABSOLUTE",
        }
    )
    assert spool.is_low_stock is True


def test_low_stock_percentage():
    spool = Spool.from_api(
        {
            "id": 1,
            "weightInitial": 1000,
            "weightRemaining": 150,
            "lowStockThreshold": 20,
            "lowStockThresholdType": "PERCENTAGE",
        }
    )
    # 150/1000 = 15% <= 20% -> stock faible
    assert spool.is_low_stock is True


def test_not_low_stock_without_threshold():
    spool = Spool.from_api({"id": 1, "weightRemaining": 10})
    assert spool.is_low_stock is False
