"""Table de rangs pour le World Catalogue of Opiliones (ChecklistBank, dataset 2256).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "order"/"suborder"/"superfamily"/"family"/"subfamily"/"genus"/"species" observés sur
Opiliones) — réutilise `col_xr_cherche_rang` plutôt que dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def wco_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
