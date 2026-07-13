"""Table de rangs pour CoL (Catalogue of Life)."""

from __future__ import annotations

COL_RANKS: dict[str, str] = {
    "family": "famille", "superfamily": "super-famille", "subfamily": "sous-famille",
    "superclass": "super-classe", "class": "classe", "subclass": "sous-classe",
    "genus": "genre", "subgenus": "sous-genre", "species": "espèce",
    "megaclass": "super-classe", "gigaclass": "super-classe",
    "parvphylum": "micro-embranchement", "infraphylum": "infra-embranchement",
    "subphylum": "sous-embranchement", "phylum": "embranchement", "kingdom": "règne",
}


def col_cherche_rang(rang: str) -> str:
    return COL_RANKS.get(rang, "non classé")
