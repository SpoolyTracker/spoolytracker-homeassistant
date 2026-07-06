"""Tests unitaires du moteur de résolution de bobine (logique pure, sans HA)."""

from __future__ import annotations

import os
import sys

import pytest

# Rend le paquet importable sans installer Home Assistant.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components"))

from spoolytracker.matching import (  # noqa: E402
    MatchStatus,
    SpoolResolver,
    slot_key,
)
from spoolytracker.models import Spool  # noqa: E402


def make_spool(spool_id: int, **kw) -> Spool:
    return Spool(id=spool_id, **kw)


@pytest.fixture
def spools() -> list[Spool]:
    return [
        make_spool(1, brand="Bambu", material="PETG", color_name="black"),
        make_spool(2, brand="Bambu", material="PLA", color_name="white"),
        make_spool(3, brand="Polymaker", material="PETG", color_name="black"),
    ]


def test_slot_key_variants():
    assert slot_key("Bambu P1S", 1, 3) == "bambu p1s|ams1/slot3"
    assert slot_key("Bambu P1S", external=True) == "bambu p1s|external"
    assert slot_key("X") == "x|default"


def test_s1_direct(spools):
    r = SpoolResolver().resolve({"spool_id": 2, "grams_used": 10}, spools)
    assert r.status is MatchStatus.RESOLVED
    assert r.spool.id == 2
    assert r.strategy == "direct"


def test_s1_direct_unknown_id_not_found(spools):
    r = SpoolResolver().resolve({"spool_id": 999}, spools)
    assert r.status is MatchStatus.NOT_FOUND


def test_s2_slot_map(spools):
    smap = {slot_key("Bambu P1S", 1, 3): "3"}
    r = SpoolResolver().resolve(
        {"printer_name": "Bambu P1S", "ams_unit": 1, "ams_slot": 3},
        spools,
        slot_map=smap,
    )
    assert r.status is MatchStatus.RESOLVED
    assert r.spool.id == 3
    assert r.strategy == "slot_map"


def test_s4_active_select_for_slot(spools):
    key = slot_key("Bambu P1S", 1, 3)
    r = SpoolResolver().resolve(
        {"printer_name": "Bambu P1S", "ams_unit": 1, "ams_slot": 3},
        spools,
        active_selects={key: "1"},
    )
    assert r.status is MatchStatus.RESOLVED
    assert r.spool.id == 1
    assert r.strategy == "active_select"


def test_s4_global_select_fallback(spools):
    r = SpoolResolver().resolve(
        {"printer_name": "Autre"},
        spools,
        active_selects={"__global__": "2"},
    )
    assert r.spool.id == 2
    assert r.strategy == "active_select"


def test_s3_metadata_unique(spools):
    r = SpoolResolver().resolve(
        {"material": "PLA", "brand": "Bambu"}, spools
    )
    assert r.status is MatchStatus.RESOLVED
    assert r.spool.id == 2
    assert r.strategy == "metadata"


def test_s3_metadata_ambiguous_refused(spools):
    # PETG + black correspond aux bobines 1 et 3.
    r = SpoolResolver().resolve({"material": "PETG", "color": "black"}, spools)
    assert r.status is MatchStatus.AMBIGUOUS
    assert {s.id for s in r.candidates} == {1, 3}


def test_s3_metadata_ambiguous_allowed(spools):
    r = SpoolResolver().resolve(
        {"material": "PETG", "color": "black"}, spools, allow_ambiguous=True
    )
    assert r.status is MatchStatus.RESOLVED
    assert r.strategy == "metadata_ambiguous"
    assert r.spool.id in (1, 3)


def test_priority_direct_beats_metadata(spools):
    r = SpoolResolver().resolve(
        {"spool_id": 1, "material": "PLA"}, spools
    )
    assert r.spool.id == 1
    assert r.strategy == "direct"


def test_disabled_metadata_strategy(spools):
    r = SpoolResolver(enable_metadata=False).resolve(
        {"material": "PLA", "brand": "Bambu"}, spools
    )
    assert r.status is MatchStatus.NOT_FOUND


def test_no_criteria_not_found(spools):
    r = SpoolResolver().resolve({"grams_used": 5}, spools)
    assert r.status is MatchStatus.NOT_FOUND


def test_profile_substring_match(spools):
    r = SpoolResolver().resolve(
        {"filament_profile": "Bambu PLA White"}, spools
    )
    assert r.status is MatchStatus.RESOLVED
    assert r.spool.id == 2
