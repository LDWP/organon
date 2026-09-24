"""Rank table for Hesperomys.

The GraphQL `Rank` enum mixes standard ranks and nomenclatural
bibliography ranks (`synonym_genus`, `informal_species`…) that match no
Wikipedia rank: only standard ones are mapped, the rest is None.
"""

from __future__ import annotations

# Kingdom-level ranks and `domain` are mapped but excluded from the rank
# chain by the adapter: the kingdom is stored in struct.kingdom, not
# duplicated in struct.ranks (same as ITIS).
HESPEROMYS_RANKS: dict[str, str] = {
    "domain": "domaine",
    "superkingdom": "super-règne",
    "kingdom": "règne",
    "subkingdom": "sous-règne",
    "infrakingdom": "infra-règne",
    "superphylum": "super-embranchement",
    "phylum": "embranchement",
    "subphylum": "sous-embranchement",
    "infraphylum": "infra-embranchement",
    "superclass": "super-classe",
    "class_": "classe",
    "subclass": "sous-classe",
    "infraclass": "infra-classe",
    "supercohort": "super-cohorte",
    "cohort": "cohorte",
    "subcohort": "sous-cohorte",
    "superorder": "super-ordre",
    "order": "ordre",
    "suborder": "sous-ordre",
    "infraorder": "infra-ordre",
    "parvorder": "parvordre",
    "superfamily": "super-famille",
    "family": "famille",
    "subfamily": "sous-famille",
    "tribe": "tribu",
    "subtribe": "sous-tribu",
    "infratribe": "infra-tribu",
    "division": "division",
    "genus": "genre",
    "subgenus": "sous-genre",
    "species": "espèce",
    "subspecies": "sous-espèce",
    "variety": "variété",
    "subvariety": "sous-variété",
    "form": "forme",
}


def hesperomys_to_wp_rank(rank: str | None) -> str | None:
    """Return the Wikipedia rank of a Hesperomys rank, or None."""
    if not rank:
        return None
    return HESPEROMYS_RANKS.get(rank)
