"""Table de rangs pour FishBase (ChecklistBank, dataset `1010`).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "parvphylum"/"gigaclass"/"superclass"/"class"/"order"/"family"/"subfamily"/"genus"/
"species" observés sur des poissons osseux) — réutilise `col_xr_cherche_rang` plutôt que
dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def fishbase_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
