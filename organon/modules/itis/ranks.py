"""Tables de correspondance de rangs/règnes ITIS -> Wikipédia."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

# ITIS classe "Chromista" sous "algue", contrairement au KINGDOM_MAP partagé (qui donne
# "protiste") : ITIS ne range pas les mêmes taxons sous Chromista que GBIF, d'où une table
# spécifique plutôt que la table partagée (celle-ci sert de règle par défaut raisonnable pour
# les nouveaux modules, pas une vérité universelle).
ITIS_REGNES: dict[str, str] = {
    "Animalia": "animal",
    "Archaea": "archaea",
    "Bacteria": "bactérie",
    "Fungi": "champignon",
    "Plantae": "végétal",
    "Protozoa": "protiste",
    "Chromista": "algue",
}


def itis_cherche_regne(regne: str) -> str:
    if regne in ITIS_REGNES:
        return ITIS_REGNES[regne]
    return _SHARED_KINGDOM_MAP.get(regne, "neutre")


# Rang ITIS (rankName tel que renvoyé par l'API) -> rang Wikipédia. Les clés
# 'null'/'null1'/'null2' sont des espaces réservés qui ne correspondent à aucune valeur
# réelle jamais renvoyée par l'API ITIS : rameau/subter-classe/épifamille sont donc
# inatteignables en pratique, mais gardés pour rester cohérent avec les autres tables de
# rangs (GBIF/WoRMS/IRMNG/AlgaeBase/CoL) qui listent ces mêmes rangs.
ITIS_WP: dict[str, str] = {
    "Clade": "clade", "Type": "type", "Group": "groupe", "Unspecified": "non-classé",
    "Subform": "sous-forme", "Form": "forme", "Variety": "variété", "Pathovar": "pathovar",
    "Cultivar": "cultivar", "Subspecies": "sous-espèce", "Hybrid": "hybride", "Species": "espèce",
    "Subserie": "sous-série", "Serie": "série", "Subsection": "sous-section", "Section": "section",
    "Subgenus": "sous-genre", "Genus": "genre", "Subtribe": "sous-tribu", "Tribe": "tribu",
    "Supertribe": "super-tribu", "Infratribe": "infra-tribu", "Subfamily": "sous-famille",
    "Family": "famille", "null2": "épifamille", "Superfamily": "super-famille",
    "Microorder": "micro-ordre", "Infraorder": "infra-ordre", "Suborder": "sous-ordre",
    "Order": "ordre", "Superorder": "super-ordre", "Subcohort": "sous-cohorte",
    "Cohort": "cohorte", "Supercohort": "super-cohorte", "null1": "subter-classe",
    "Infraclass": "infra-classe", "Subclass": "sous-classe", "Class": "classe",
    "Superclass": "super-classe", "Microphylum": "micro-embranchement",
    "Infraphylum": "infra-embranchement", "Subphylum": "sous-embranchement",
    "Phylum": "embranchement", "Superphylum": "super-embranchement",
    "Infradivision": "infra-division", "Subdivision": "sous-division", "Division": "division",
    "Superdivision": "super-division", "Infrakingdom": "infra-règne", "null": "rameau",
    "Subkingdom": "sous-règne", "Kingdom": "règne", "Superkingdom": "super-règne",
    "Subdomain": "sous-domaine", "Domain": "domaine", "Superdomain": "super-domaine",
    "Empire": "empire",
}

# Rangs exclus de la chaîne des rangs supérieurs : le "règne" est stocké séparément dans
# struct.regne, pas dupliqué dans struct.rangs.
RANGS_REGNE = {"royaume", "règne"}


def itis_cherche_rang(rang: str) -> str:
    return ITIS_WP.get(rang, "NOTFOUND")
