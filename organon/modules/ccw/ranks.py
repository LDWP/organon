"""Table de rangs pour la Checklist of the Collembola of the World (ChecklistBank, dataset 2130).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "class"/"order"/"superfamily"/"family"/"subfamily"/"tribe"/"genus"/"species" observés
sur Entomobrya/Isotoma) — réutilise `col_xr_cherche_rang` plutôt que dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def ccw_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
