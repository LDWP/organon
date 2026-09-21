"""Table de rangs pour GTDB (ChecklistBank, dataset 2214).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "domain"/"phylum"/"class"/"order"/"family"/"genus"/"species" observés sur des
lignées bactériennes et archées) — réutilise `col_xr_cherche_rang` plutôt que dupliquer la même
table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def gtdb_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
