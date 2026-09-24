"""IRMNG to Wikipedia rank and kingdom tables.

IRMNG shares WoRMS's rank family (same Aphia/VLIZ platform) with a few
specific ones (e.g. 'Parvorder'). As for WoRMS, a few very specialized
ranks are missing from `core/data/ranks.yaml` and give None rather than
fail.
"""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

_IRMNG_RANKS: dict[str, str] = {
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

# Kingdoms keeping the "règne" rank in the chain besides struct.kingdom
# (as WoRMS, see organon/modules/wrms/ranks.py).
KINGDOMS_KEPT_IN_CHAIN = {"algue", "protiste"}

_IRMNG_KINGDOMS: dict[str, str] = {
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


def irmng_to_wp_rank(rank: str) -> str | None:
    """Return the Wikipedia rank of an IRMNG rank, or None."""
    return _IRMNG_RANKS.get(rank)


def irmng_charter_kingdom(name: str) -> str:
    """Return the Organon domain of an IRMNG kingdom."""
    if name in _IRMNG_KINGDOMS:
        return _IRMNG_KINGDOMS[name]
    return _SHARED_KINGDOM_MAP.get(name, "neutre")
