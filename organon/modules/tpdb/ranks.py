"""Table de rangs pour l'API PBDB (Paleobiology Database, `paleobiodb.org/data1.2`) en mode
`vocab=pbdb` — noms de rangs en anglais simple (`"species"`, `"family"`…). `"unranked clade"`
est une valeur réelle et fréquente en paléontologie (groupes cladistiques sans rang linnéen,
ex. Dinosauria, Theropoda) — mappée sur "clade", cohérent avec le traitement des autres
modules (GBIF `CLADE`, AlgaeBase `clade`, etc.)."""

from __future__ import annotations

TPDB_RANKS: dict[str, str] = {
    "unranked clade": "clade",
    "subspecies": "sous-espèce",
    "species": "espèce",
    "subgenus": "sous-genre",
    "genus": "genre",
    "subtribe": "sous-tribu",
    "tribe": "tribu",
    "subfamily": "sous-famille",
    "family": "famille",
    "superfamily": "super-famille",
    "infraorder": "infra-ordre",
    "suborder": "sous-ordre",
    "order": "ordre",
    "superorder": "super-ordre",
    "infraclass": "infra-classe",
    "subclass": "sous-classe",
    "class": "classe",
    "superclass": "super-classe",
    "infraphylum": "infra-embranchement",
    "subphylum": "sous-embranchement",
    "phylum": "embranchement",
    "superphylum": "super-embranchement",
    "subkingdom": "sous-règne",
    "kingdom": "règne",
}


def tpdb_rang(rank: str) -> str:
    return TPDB_RANKS.get(rank, f"NOTFOUND-{rank}")
