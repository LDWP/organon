"""Table de rangs pour Bryonames (ChecklistBank, dataset 170394).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "subkingdom"/"phylum"/"class"/"subclass"/"order"/"family"/"genus"/"species" observés
sur des genres de mousses/hépatiques/anthocérotes) — réutilise `col_xr_cherche_rang` plutôt que
dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def bryonames_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
