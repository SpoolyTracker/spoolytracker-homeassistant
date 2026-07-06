"""Résolution de la bobine : les 5 stratégies d'identification.

Logique PURE (aucune dépendance à Home Assistant hors types simples) pour rester
testable unitairement. Le service `log_consumption` appelle `SpoolResolver.resolve`
et agit selon le `MatchResult` renvoyé.

Ordre de priorité, du plus fiable au plus automatique :
    S1 spool_id direct  >  S2 mapping slot  >  S4 select actif  >  S3 metadata
S3 (metadata) ne loggue jamais automatiquement en cas d'ambiguïté sauf option.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .models import Spool


class MatchStatus(Enum):
    RESOLVED = "resolved"       # exactement une bobine
    NOT_FOUND = "not_found"     # aucune bobine -> fallback S5
    AMBIGUOUS = "ambiguous"     # plusieurs bobines et ambiguïté non autorisée


@dataclass(slots=True)
class MatchResult:
    status: MatchStatus
    spool: Spool | None = None
    strategy: str | None = None            # quelle stratégie a résolu
    candidates: list[Spool] = field(default_factory=list)
    reason: str = ""


def slot_key(
    printer: str,
    ams_unit: Any = None,
    ams_slot: Any = None,
    external: bool = False,
) -> str:
    """Clé normalisée d'un slot, utilisée par le mapping et les selects.

    Exemples : "bambu p1s|ams1/slot3", "bambu p1s|external".
    """
    printer_norm = (printer or "").strip().lower()
    if external:
        return f"{printer_norm}|external"
    if ams_unit is not None and ams_slot is not None:
        return f"{printer_norm}|ams{ams_unit}/slot{ams_slot}"
    if ams_slot is not None:
        return f"{printer_norm}|slot{ams_slot}"
    return f"{printer_norm}|default"


def _norm(value: Any) -> str:
    return str(value).strip().lower() if value not in (None, "") else ""


class SpoolResolver:
    """Applique les stratégies activées dans l'ordre de priorité."""

    def __init__(
        self,
        *,
        enable_slot: bool = True,
        enable_select: bool = True,
        enable_metadata: bool = True,
    ) -> None:
        self.enable_slot = enable_slot
        self.enable_select = enable_select
        self.enable_metadata = enable_metadata

    def resolve(
        self,
        call: dict[str, Any],
        spools: list[Spool],
        *,
        slot_map: dict[str, Any] | None = None,
        active_selects: dict[str, Any] | None = None,
        allow_ambiguous: bool = False,
    ) -> MatchResult:
        slot_map = slot_map or {}
        active_selects = active_selects or {}
        by_id = {s.id: s for s in spools}

        def as_spool(spool_id: Any) -> Spool | None:
            try:
                return by_id.get(int(spool_id))
            except (TypeError, ValueError):
                return None

        # --- S1 : spool_id direct -------------------------------------------
        if call.get("spool_id") not in (None, ""):
            spool = as_spool(call["spool_id"])
            if spool:
                return MatchResult(MatchStatus.RESOLVED, spool, strategy="direct")
            return MatchResult(
                MatchStatus.NOT_FOUND,
                strategy="direct",
                reason=f"spool_id {call['spool_id']} introuvable dans le stock",
            )

        key = None
        if call.get("printer_name"):
            key = slot_key(
                call["printer_name"],
                call.get("ams_unit"),
                call.get("ams_slot"),
                bool(call.get("external")),
            )

        # --- S2 : mapping printer/AMS/slot ----------------------------------
        if self.enable_slot and key and key in slot_map:
            spool = as_spool(slot_map[key])
            if spool:
                return MatchResult(MatchStatus.RESOLVED, spool, strategy="slot_map")

        # --- S4 : select actif pour ce slot (ou global) ---------------------
        if self.enable_select:
            picked = None
            if key and active_selects.get(key) not in (None, "", "none"):
                picked = active_selects.get(key)
            elif active_selects.get("__global__") not in (None, "", "none"):
                picked = active_selects.get("__global__")
            spool = as_spool(picked) if picked is not None else None
            if spool:
                return MatchResult(MatchStatus.RESOLVED, spool, strategy="active_select")

        # --- S3 : metadata (matière / couleur / marque / profil / ref) ------
        if self.enable_metadata:
            candidates = self._match_metadata(call, spools)
            if len(candidates) == 1:
                return MatchResult(
                    MatchStatus.RESOLVED, candidates[0], strategy="metadata"
                )
            if len(candidates) > 1:
                if allow_ambiguous:
                    return MatchResult(
                        MatchStatus.RESOLVED,
                        candidates[0],
                        strategy="metadata_ambiguous",
                        candidates=candidates,
                        reason=f"{len(candidates)} bobines correspondaient ; "
                        "allow_ambiguous_match a sélectionné la première",
                    )
                return MatchResult(
                    MatchStatus.AMBIGUOUS,
                    candidates=candidates,
                    strategy="metadata",
                    reason=f"{len(candidates)} bobines correspondent aux critères",
                )

        # --- S5 : rien trouvé -> fallback -----------------------------------
        return MatchResult(
            MatchStatus.NOT_FOUND,
            strategy="none",
            reason="aucune stratégie n'a permis d'identifier une bobine",
        )

    @staticmethod
    def _match_metadata(call: dict[str, Any], spools: list[Spool]) -> list[Spool]:
        """Filtre les bobines par métadonnées. Un critère absent est ignoré.

        Le profil filament (ex. « Bambu PETG HF Black ») est comparé en sous-chaîne
        contre marque/matière/couleur car il agrège souvent ces infos.
        """
        material = _norm(call.get("material"))
        color = _norm(call.get("color"))
        brand = _norm(call.get("brand"))
        profile = _norm(call.get("filament_profile"))
        reference = _norm(call.get("spool_reference"))

        # Si aucun critère exploitable, pas de matching metadata.
        if not any((material, color, brand, profile, reference)):
            return []

        def matches(spool: Spool) -> bool:
            checks: list[Callable[[], bool]] = []
            if material:
                checks.append(lambda: _norm(spool.material) == material)
            if brand:
                checks.append(lambda: _norm(spool.brand) == brand)
            if color:
                checks.append(
                    lambda: color
                    in (
                        _norm(spool.color_name),
                        _norm(spool.color),
                        _norm(spool.color_hex),
                    )
                )
            if reference:
                checks.append(lambda: _norm(spool.spool_reference) == reference)
            if profile:
                blob = " ".join(
                    _norm(x)
                    for x in (
                        spool.brand,
                        spool.material,
                        spool.color_name,
                        spool.color,
                        spool.spool_reference,
                    )
                )
                # Tous les mots significatifs du profil doivent apparaître.
                words = [w for w in profile.split() if len(w) > 2]
                checks.append(lambda: all(w in blob for w in words) if words else False)

            return all(check() for check in checks)

        return [s for s in spools if matches(s)]
