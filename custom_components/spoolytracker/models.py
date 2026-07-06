"""Modèles/normalisation des données SpoolyTracker.

Isole le reste de l'intégration du format brut renvoyé par l'API. `Spool`
aplatit la structure imbriquée (brand.name, material.name, …) en champs simples
et fournit un libellé lisible utilisé par les entités select et les logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class Spool:
    """Vue normalisée d'une bobine (filament) SpoolyTracker."""

    id: int
    spool_reference: str | None = None
    brand: str | None = None
    material: str | None = None
    color: str | None = None
    color_hex: str | None = None
    color_name: str | None = None
    weight_initial: float | None = None
    weight_remaining: float | None = None
    low_stock_threshold: float | None = None
    low_stock_threshold_type: str | None = None
    is_locked: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Spool":
        brand = data.get("brand") or {}
        material = data.get("material") or {}
        return cls(
            id=int(data["id"]),
            spool_reference=data.get("spoolReference"),
            brand=(brand.get("name") if isinstance(brand, dict) else None),
            material=(material.get("name") if isinstance(material, dict) else None),
            color=data.get("color"),
            color_hex=data.get("colorHex"),
            color_name=data.get("colorName"),
            weight_initial=_num(data.get("weightInitial")),
            weight_remaining=_num(data.get("weightRemaining")),
            low_stock_threshold=_num(data.get("lowStockThreshold")),
            low_stock_threshold_type=data.get("lowStockThresholdType"),
            is_locked=bool(data.get("isLocked")),
            raw=data,
        )

    @property
    def label(self) -> str:
        """Libellé lisible pour les selects et les logs.

        Ex. « #12 · Bambu PETG Noir · 250 g » (le poids restant est ajouté
        quand il est connu).
        """
        parts = [
            p
            for p in (self.brand, self.material, self.color_name or self.color)
            if p
        ]
        detail = " ".join(parts) if parts else (self.spool_reference or "bobine")
        label = f"#{self.id} · {detail}"
        if self.weight_remaining is not None:
            label += f" · {round(self.weight_remaining)} g"
        return label

    @property
    def is_low_stock(self) -> bool:
        """Réplique la logique serveur de stock faible."""
        threshold = self.low_stock_threshold
        remaining = self.weight_remaining
        if not threshold or remaining is None:
            return False
        if self.low_stock_threshold_type == "PERCENTAGE":
            initial = self.weight_initial or 0
            if initial <= 0:
                return False
            return (remaining / initial) * 100 <= threshold
        return remaining <= threshold


@dataclass(slots=True)
class SpoolyTrackerData:
    """Instantané renvoyé par le coordinator."""

    spools: list[Spool] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    last_consumption: dict[str, Any] | None = None

    def spool_by_id(self, spool_id: int | str) -> Spool | None:
        try:
            target = int(spool_id)
        except (TypeError, ValueError):
            return None
        return next((s for s in self.spools if s.id == target), None)
