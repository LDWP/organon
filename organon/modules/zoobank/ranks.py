"""Table de rangs pour ZooBank (ChecklistBank, dataset 2037).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "species"/"genus"/"class" observés sur des taxons animaux réels) — réutilise
`col_xr_cherche_rang` plutôt que dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def zoobank_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
