"""Table de rangs pour GRIN Taxonomy (ChecklistBank, dataset 2018).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "family"/"subfamily"/"tribe"/"subtribe"/"genus"/"species"/"subspecies" observés sur
Poaceae/Zea) — réutilise `col_xr_cherche_rang` plutôt que dupliquer la même table, comme
`bryonames`."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def grin_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
