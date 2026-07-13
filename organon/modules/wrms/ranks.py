"""Tables de correspondance de rangs/règnes WoRMS -> Wikipédia. Quelques rangs marins très
spécialisés (ex. 'giga-classe', 'parv-embranchement') ne sont pas encore présents dans
core/data/ranks.yaml : wp_nom_rang() etc. retournent alors "NOTFOUND" pour ces rangs plutôt
que de planter. Complément de ranks.yaml à prévoir si besoin."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

WRMS_RANGS: dict[str, str] = {
    "Clade": "clade", "Type": "type", "Group": "groupe", "Unspecified": "non-classé",
    "Subform": "sous-forme", "Form": "forme", "Variety": "variété", "Pathovar": "pathovar",
    "Cultivar": "cultivar", "Subspecies": "sous-espèce", "Hybrid": "hybride", "Species": "espèce",
    "Subserie": "sous-série", "Serie": "série", "Subsection": "sous-section", "Section": "section",
    "Subgenus": "sous-genre", "Genus": "genre", "Subtribe": "sous-tribu", "Tribe": "tribu",
    "Supertribe": "super-tribu", "Infratribe": "infra-tribu", "Subfamily": "sous-famille",
    "Family": "famille", "null2": "épifamille", "Superfamily": "super-famille",
    "Parvorder": "parv-ordre", "Microorder": "micro-ordre", "Infraorder": "infra-ordre",
    "Suborder": "sous-ordre", "Order": "ordre", "Superorder": "super-ordre",
    "Subcohort": "sous-cohorte", "Cohort": "cohorte", "Supercohort": "super-cohorte",
    "Subterclass": "subter-classe", "Infraclass": "infra-classe", "Subclass": "sous-classe",
    "Class": "classe", "Superclass": "super-classe", "Megaclass": "super-classe",
    "Gigaclass": "giga-classe", "Parvphylum": "parv-embranchement",
    "Microphylum": "micro-embranchement", "Infraphylum": "infra-embranchement",
    "Subphylum": "sous-embranchement", "Phylum": "embranchement",
    "Superphylum": "super-embranchement", "Infradivision": "infra-division",
    "Subdivision": "sous-division", "Division": "division",
    "Subphylum Subdivision": "sous-division", "Phylum Division": "division",
    "Superdivision": "super-division", "Infrakingdom": "infra-règne", "null": "rameau",
    "Subkingdom": "sous-règne", "Kingdom": "règne", "Superkingdom": "super-règne",
    "Subdomain": "sous-domaine", "Domain": "domaine", "Superdomain": "super-domaine",
    "Empire": "empire",
}

RANGS_REGNE = {"royaume", "règne"}

# Règnes pour lesquels le rang "règne" est conservé dans la chaîne de classification en plus
# de struct.regne (utile pour algue/protiste, où la charte à elle seule ne suffit pas à situer
# le taxon dans l'arbre).
CHARTES_GARDENT_REGNE = {"algue", "protiste"}

WRMS_REGNES: dict[str, str] = {
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


def wrms_rang(rang: str) -> str:
    return WRMS_RANGS.get(rang, f"NOTFOUND-{rang}")


def wrms_charte(nom: str) -> str:
    if nom in WRMS_REGNES:
        return WRMS_REGNES[nom]
    return _SHARED_KINGDOM_MAP.get(nom, "neutre")
