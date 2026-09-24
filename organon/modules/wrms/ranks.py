"""WoRMS to Wikipedia rank and kingdom tables.

A few very specialized marine ranks are missing from
`core/data/ranks.yaml`: the helpers then return None rather than fail.
"""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

_WRMS_RANKS: dict[str, str] = {
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
    "Parvorder": "parv-ordre",
    "Microorder": "micro-ordre",
    "Infraorder": "infra-ordre",
    "Suborder": "sous-ordre",
    "Order": "ordre",
    "Superorder": "super-ordre",
    "Subcohort": "sous-cohorte",
    "Cohort": "cohorte",
    "Supercohort": "super-cohorte",
    "Subterclass": "subter-classe",
    "Infraclass": "infra-classe",
    "Subclass": "sous-classe",
    "Class": "classe",
    "Superclass": "super-classe",
    "Megaclass": "super-classe",
    "Gigaclass": "giga-classe",
    "Parvphylum": "parv-embranchement",
    "Microphylum": "micro-embranchement",
    "Infraphylum": "infra-embranchement",
    "Subphylum": "sous-embranchement",
    "Phylum": "embranchement",
    "Superphylum": "super-embranchement",
    "Infradivision": "infra-division",
    "Subdivision": "sous-division",
    "Division": "division",
    "Subphylum Subdivision": "sous-division",
    "Phylum Division": "division",
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

KINGDOM_RANKS = {"royaume", "règne"}

# Kingdoms keeping the "règne" rank in the classification chain besides
# struct.kingdom (useful for algae and protists, where the domain alone
# does not place the taxon in the tree).
KINGDOMS_KEPT_IN_CHAIN = {"algue", "protiste"}

_WRMS_KINGDOMS: dict[str, str] = {
    "Animalia": "animal",
    "Archaea": "archaea",
    "Bacteria": "bactérie",
    "Fungi": "champignon",
    "Plantae": "végétal",
    "Viruses": "virus",
    "Incertae sedis": "neutre",
    "Protozoa": "protiste",
    "Chromista": "protiste",
}


def wrms_to_wp_rank(rank: str) -> str | None:
    """Return the Wikipedia rank of a WoRMS rank, or None."""
    return _WRMS_RANKS.get(rank)


def wrms_charter_kingdom(name: str) -> str:
    """Return the Organon domain of a WoRMS kingdom."""
    if name in _WRMS_KINGDOMS:
        return _WRMS_KINGDOMS[name]
    return _SHARED_KINGDOM_MAP.get(name, "neutre")
