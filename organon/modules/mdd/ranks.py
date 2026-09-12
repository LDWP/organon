"""Table de rangs pour la Mammal Diversity Database (ChecklistBank, dataset 9802).

Même plateforme et même vocabulaire de rangs que la Catalogue of Life Extended Release (vérifié
en direct : "class"/"subclass"/"order"/"suborder"/"family"/"genus"/"species"/"subspecies"
observés sur Ornithorhynchus anatinus et Canis lupus familiaris) — réutilise
`col_xr_cherche_rang` plutôt que dupliquer la même table."""

from __future__ import annotations

from organon.modules.col_xr.ranks import col_xr_cherche_rang


def mdd_cherche_rang(rang: str) -> str:
    return col_xr_cherche_rang(rang)
