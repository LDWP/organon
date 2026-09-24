"""Rank and kingdom tables for AlgaeBase."""

from __future__ import annotations

ALGAEBASE_RANKS: dict[str, str] = {
    "clade": "clade",
    "type": "type",
    "group": "groupe",
    "unspecified": "non-classé",
    "subform": "sous-forme",
    "form": "forme",
    "forma": "forme",
    "variety": "variété",
    "pathovar": "pathovar",
    "cultivar": "cultivar",
    "subspecies": "sous-espèce",
    "hybrid": "hybride",
    "species": "espèce",
    "subserie": "sous-série",
    "serie": "série",
    "subsection": "sous-section",
    "section": "section",
    "subgenus": "sous-genre",
    "genus": "genre",
    "subtribe": "sous-tribu",
    "tribe": "tribu",
    "supertribe": "super-tribu",
    "infratribe": "infra-tribu",
    "subfamily": "sous-famille",
    "family": "famille",
    "null2": "épifamille",
    "superfamily": "super-famille",
    "microorder": "micro-ordre",
    "infraorder": "infra-ordre",
    "suborder": "sous-ordre",
    "order": "ordre",
    "superorder": "super-ordre",
    "subcohort": "sous-cohorte",
    "cohort": "cohorte",
    "supercohort": "super-cohorte",
    "subterclass": "subter-classe",
    "infraclass": "infra-classe",
    "subclass": "sous-classe",
    "class": "classe",
    "superclass": "super-classe",
    "megaclass": "super-classe",
    "microphylum": "micro-embranchement",
    "infraphylum": "infra-embranchement",
    "subphylum": "sous-embranchement",
    "phylum": "embranchement",
    "superphylum": "super-embranchement",
    "infradivision": "infra-division",
    "subdivision": "sous-division",
    "division": "division",
    "subphylum subdivision": "sous-division",
    "phylum division": "division",
    "superdivision": "super-division",
    "infrakingdom": "infra-règne",
    "null": "rameau",
    "subkingdom": "sous-règne",
    "kingdom": "règne",
    "superkingdom": "super-règne",
    "subdomain": "sous-domaine",
    "domain": "domaine",
    "superdomain": "super-domaine",
    "empire": "empire",
    "unknown": "non-classé",
}


def algaebase_to_wp_rank(rank: str) -> str | None:
    """Return the Wikipedia rank of an AlgaeBase rank, or None."""
    return ALGAEBASE_RANKS.get((rank or "").lower())


def algaebase_charter_kingdom(phylum: str, kingdom: str) -> str:
    """Return the Organon domain from the raw dwc kingdom and phylum.

    Not from the already French-translated version.
    """
    if kingdom.lower() == "eubacteria":
        return "bactérie"
    if phylum.lower() == "tracheophyta":
        return "végétal"
    if kingdom.lower() == "protozoa":
        return "protiste"
    return "algue"
