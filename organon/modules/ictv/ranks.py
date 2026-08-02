"""Table de correspondance rangs ICTV (colonnes de organon/core/data/ictv_taxonomy.tsv) -> rangs
Wikipédia (organon/core/data/ranks.yaml). `Subkingdom` n'a volontairement aucune entrée :
entièrement vide dans le MSL courant (voir scripts/build_ictv_taxonomy.py) — à ajouter le jour où
l'ICTV l'utilise réellement."""

from __future__ import annotations

ICTV_RANGS: dict[str, str] = {
    "Realm": "royaume",
    "Subrealm": "sous-royaume",
    "Kingdom": "kingdom",
    "Phylum": "phylum",
    "Subphylum": "sous-phylum",
    "Class": "classe",
    "Subclass": "sous-classe",
    "Order": "ordre",
    "Suborder": "sous-ordre",
    "Family": "famille",
    "Subfamily": "sous-famille",
    "Genus": "genre",
    "Subgenus": "sous-genre",
    "Species": "espèce",
}


def ictv_rang(colonne: str) -> str:
    return ICTV_RANGS.get(colonne, f"NOTFOUND-{colonne}")
