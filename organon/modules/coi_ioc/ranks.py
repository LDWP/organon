"""Table de rangs pour la classification COI/IOC (ChecklistBank, dataset 2036).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "infraclass"/"order"/"family"/"genus"/"species"/"subspecies" observés sur des
oiseaux) — réutilise `col_xr_cherche_rang` plutôt que dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def coi_ioc_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
