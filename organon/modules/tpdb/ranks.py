"""Rank table for the PBDB API in `vocab=pbdb` mode.

Plain English rank names (`"species"`, `"family"`…). `"unranked clade"`
is a real and frequent value in paleontology (cladistic groups with no
Linnaean rank, e.g. Dinosauria), mapped to "clade" like the other
modules (GBIF `CLADE`, AlgaeBase `clade`).
"""

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


def tpdb_to_wp_rank(rank: str) -> str | None:
    """Return the Wikipedia rank of a PBDB rank, or None."""
    return TPDB_RANKS.get(rank)
