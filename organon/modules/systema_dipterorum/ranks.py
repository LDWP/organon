"""Table de rangs pour Systema Dipterorum (ChecklistBank, dataset 1101).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "order"/"family"/"subfamily"/"tribe"/"genus"/"subgenus"/"species" observés sur des
genres de Diptera) — réutilise `col_xr_cherche_rang` plutôt que dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def systema_dipterorum_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
