"""ITIS to Wikipedia rank and kingdom tables."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

# ITIS files "Chromista" under "algue", unlike the shared KINGDOM_MAP
# ("protiste"): it does not put the same taxa under Chromista as GBIF
# does, hence a specific table (the shared one is only a reasonable
# default for new modules).
_ITIS_KINGDOMS: dict[str, str] = {
    "Animalia": "animal",
    "Archaea": "archaea",
    "Bacteria": "bactérie",
    "Fungi": "champignon",
    "Plantae": "végétal",
    "Protozoa": "protiste",
    "Chromista": "algue",
}


def itis_lookup_kingdom(kingdom: str) -> str:
    """Return the Organon domain of an ITIS kingdom."""
    if kingdom in _ITIS_KINGDOMS:
        return _ITIS_KINGDOMS[kingdom]
    return _SHARED_KINGDOM_MAP.get(kingdom, "neutre")


# ITIS rank (rankName as the API returns it) to Wikipedia rank. The keys
# null, null1 and null2 are placeholders matching no real API value, so
# rameau, subter-classe and épifamille are unreachable; kept for
# consistency with the other rank tables (GBIF, WoRMS, IRMNG, AlgaeBase,
# CoL).
ITIS_WP: dict[str, str] = {
    "Clade": "clade",
    "Type": "type",
    "Group": "groupe",
    "Unspecified": "non-classé",
    "Subform": "sous-forme",
    "Form": "forme",
    "Variety": "variété",
    "Pathovar": "pathovar",
    "Cultivar": "cultivar",
    "Subspecies": "sous-espèce",
    "Hybrid": "hybride",
    "Species": "espèce",
    "Subserie": "sous-série",
    "Serie": "série",
    "Subsection": "sous-section",
    "Section": "section",
    "Subgenus": "sous-genre",
    "Genus": "genre",
    "Subtribe": "sous-tribu",
    "Tribe": "tribu",
    "Supertribe": "super-tribu",
    "Infratribe": "infra-tribu",
    "Subfamily": "sous-famille",
    "Family": "famille",
    "null2": "épifamille",
    "Superfamily": "super-famille",
    "Microorder": "micro-ordre",
    "Infraorder": "infra-ordre",
    "Suborder": "sous-ordre",
    "Order": "ordre",
    "Superorder": "super-ordre",
    "Subcohort": "sous-cohorte",
    "Cohort": "cohorte",
    "Supercohort": "super-cohorte",
    "null1": "subter-classe",
    "Infraclass": "infra-classe",
    "Subclass": "sous-classe",
    "Class": "classe",
    "Superclass": "super-classe",
    "Microphylum": "micro-embranchement",
    "Infraphylum": "infra-embranchement",
    "Subphylum": "sous-embranchement",
    "Phylum": "embranchement",
    "Superphylum": "super-embranchement",
    "Infradivision": "infra-division",
    "Subdivision": "sous-division",
    "Division": "division",
    "Superdivision": "super-division",
    "Infrakingdom": "infra-règne",
    "null": "rameau",
    "Subkingdom": "sous-règne",
    "Kingdom": "règne",
    "Superkingdom": "super-règne",
    "Subdomain": "sous-domaine",
    "Domain": "domaine",
    "Superdomain": "super-domaine",
    "Empire": "empire",
}

# Ranks excluded from the higher-rank chain: the kingdom is stored in
# struct.kingdom, not duplicated in struct.ranks.
KINGDOM_RANKS = {"royaume", "règne"}


def itis_to_wp_rank(rank: str) -> str | None:
    """Return the Wikipedia rank of an ITIS rank name, or None."""
    return ITIS_WP.get(rank)
