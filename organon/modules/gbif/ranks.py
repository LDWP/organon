"""Tables de correspondance de rangs/règnes GBIF -> Wikipédia."""

from __future__ import annotations

# GBIF utilise deux nomenclatures de rang : marqueurs abrégés (ex. "sp.") et noms de constante
# (ex. "SPECIES").
GBIF_MARKERS: dict[str, str] = {
    "dom.": "DOMAIN", "superreg.": "SUPERKINGDOM", "reg.": "KINGDOM", "subreg.": "SUBKINGDOM",
    "infrareg.": "INFRAKINGDOM", "superphyl.": "SUPERPHYLUM", "phyl.": "PHYLUM",
    "subphyl.": "SUBPHYLUM", "infraphyl.": "INFRAPHYLUM", "supercl.": "SUPERCLASS", "cl.": "CLASS",
    "subcl.": "SUBCLASS", "infracl.": "INFRACLASS", "parvcl.": "PARVCLASS",
    "superleg.": "SUPERLEGION", "leg.": "LEGION", "subleg.": "SUBLEGION",
    "infraleg.": "INFRALEGION", "supercohort": "SUPERCOHORT", "cohort": "COHORT",
    "subcohort": "SUBCOHORT", "infracohort": "INFRACOHORT", "magnord.": "MAGNORDER",
    "superord.": "SUPERORDER", "grandord.": "GRANDORDER", "ord.": "ORDER", "subord.": "SUBORDER",
    "infraord.": "INFRAORDER", "parvord.": "PARVORDER", "superfam.": "SUPERFAMILY",
    "fam.": "FAMILY", "subfam.": "SUBFAMILY", "infrafam.": "INFRAFAMILY",
    "supertrib.": "SUPERTRIBE", "trib.": "TRIBE", "subtrib.": "SUBTRIBE",
    "infratrib.": "INFRATRIBE", "supragen.": "SUPRAGENERIC_NAME", "gen.": "GENUS",
    "subgen.": "SUBGENUS", "infragen.": "INFRAGENUS", "sect.": "SECTION", "subsect.": "SUBSECTION",
    "ser.": "SERIES", "subser.": "SUBSERIES", "infrageneric": "INFRAGENERIC_NAME",
    "agg.": "SPECIES_AGGREGATE", "sp.": "SPECIES", "infrasp.": "INFRASPECIFIC_NAME",
    "grex": "GREX", "subsp.": "SUBSPECIES", "convar.": "CONVARIETY",
    "infrasubsp.": "INFRASUBSPECIFIC_NAME", "prol.": "PROLES", "race": "RACE", "natio": "NATIO",
    "ab.": "ABERRATION", "morph": "MORPH", "var.": "VARIETY", "subvar.": "SUBVARIETY",
    "f.": "FORM", "subf.": "SUBFORM", "pv.": "PATHOVAR", "biovar": "BIOVAR",
    "chemovar": "CHEMOVAR", "morphovar": "MORPHOVAR", "phagovar": "PHAGOVAR",
    "serovar": "SEROVAR", "chemoform": "CHEMOFORM", "f.sp.": "FORMA_SPECIALIS",
    "cv.": "CULTIVAR", "strain": "STRAIN",
}

# GBIF -> rang Wikipédia. GBIF_WP["KINGDOM"] vaut "royaume" (pas "règne") et
# GBIF_WP["SUBKINGDOM"] vaut "sous-royaume" (pas "sous-règne") : sans effet pratique pour
# "KINGDOM" (le champ règne emprunte un chemin de traitement séparé, voir module.py), mais
# "SUBKINGDOM" afficherait le mauvais libellé pour un taxon dont GBIF renseigne ce champ (cas
# rare, pas encore rencontré en pratique).
GBIF_WP: dict[str, str] = {
    "CLADE": "clade", "TYPE": "type", "GROUP": "groupe", "UNRANKED": "non-classé",
    "SUBFORM": "sous-forme", "FORM": "forme", "VARIETY": "variété", "PATHOVAR": "pathovar",
    "CULTIVAR": "cultivar", "SUBSPECIES": "sous-espèce", "HYBRID": "hybride", "SPECIES": "espèce",
    "SUBSERIE": "sous-série", "SERIE": "série", "SUBSECTION": "sous-section", "SECTION": "section",
    "SUBGENUS": "sous-genre", "GENUS": "genre", "SUBTRIBE": "sous-tribu", "TRIBE": "tribu",
    "SUPERTRIBE": "super-tribu", "INFRATRIBE": "infra-tribu", "SUBFAMILY": "sous-famille",
    "FAMILY": "famille", "SUPERFAMILY": "super-famille", "MICROORDER": "micro-ordre",
    "INFRAORDER": "infra-ordre", "SUBORDER": "sous-ordre", "ORDER": "ordre",
    "SUPERORDER": "super-ordre", "SUBCOHORT": "sous-cohorte", "COHORT": "cohorte",
    "SUPERCOHORT": "super-cohorte", "PARVCLASS": "subter-classe", "INFRACLASS": "infra-classe",
    "SUBCLASS": "sous-classe", "CLASS": "classe", "SUPERCLASS": "super-classe",
    "MICROPHYLUM": "micro-embranchement", "INFRAPHYLUM": "infra-embranchement",
    "SUBPHYLUM": "sous-embranchement", "PHYLUM": "embranchement",
    "SUPERPHYLUM": "super-embranchement", "INFRADIVISION": "infra-division",
    "SUBDIVISION": "sous-division", "DIVISION": "division", "INFRAKINGDOM": "infra-règne",
    "SUBKINGDOM": "sous-royaume", "KINGDOM": "royaume", "SUBDOMAIN": "sous-domaine",
    "DOMAIN": "domaine", "SUPERDOMAIN": "super-domaine", "EMPIRE": "empire",
    "NOTFOUND": "NOTFOUND",
}

# GBIF kingdom -> domaine Organon ; alias vers la table partagée `core.domains.KINGDOM_MAP`
# (aussi utilisée par ITIS/WoRMS/IRMNG), gardé ici pour rester lisible depuis ce module.
from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP  # noqa: E402


def gbif_cherche_regne(regne: str) -> str:
    return _SHARED_KINGDOM_MAP.get(regne, "neutre")


def gbif_cherche_rang(rang: str) -> str:
    return GBIF_WP.get(rang, "NOTFOUND")


def gbif_marqueur_rang(marker: str) -> str:
    return GBIF_MARKERS.get(marker, "NOTFOUND")
