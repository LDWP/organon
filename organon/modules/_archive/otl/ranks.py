"""Table de correspondance rangs/règnes Open Tree of Life -> Wikipédia.

OTL construit sa taxonomie synthétique (OTT) en fusionnant plusieurs référentiels (NCBI, GBIF,
WoRMS, IRMNG, SILVA...) en un seul arbre. Contrairement à GBIF/ITIS/WoRMS, qui exposent un
champ `kingdom` dédié, OTL ne fournit qu'une lignée plate (`lineage`, du taxon vers la racine) où
le "règne" doit être retrouvé en cherchant le premier nœud de rang `kingdom` en remontant depuis
le taxon ; à défaut (procaryotes et certains groupes de protistes, où OTL ne pose aucun rang
`kingdom` — vérifié en direct sur *Escherichia coli*, *Sulfolobus acidocaldarius* et
*Plasmodium falciparum*), le premier nœud de rang `domain`. Les noms utilisés par OTL pour ce
nœud diffèrent parfois de `core.domains.KINGDOM_MAP` (ex. "Metazoa" plutôt que "Animalia",
"Chloroplastida" plutôt que "Plantae"/"Viridiplantae") — complétés dans `OTL_KINGDOM_ALIASES`.

La lignée contient aussi de nombreux nœuds sans rang formel ("no rank", clades informels de la
synthèse OTT) et, pour certains groupes, plusieurs nœuds consécutifs de même rang formel (ex.
deux nœuds de rang "superclass" chez les tétrapodes, deux nœuds "subphylum" chez les vertébrés)
— vérifié en direct sur *Homo sapiens*. Les rangs non reconnus par `OTL_RANKS` sont simplement
ignorés (pas de "NOTFOUND") : contrairement à GBIF (jeu de rangs fermé, un rang absent est une
anomalie), l'absence de rang formel est la norme dans la lignée OTL, pas une anomalie."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP

OTL_RANKS: dict[str, str] = {
    "domain": "domaine",
    "subdomain": "sous-domaine",
    "subkingdom": "sous-règne",
    "infrakingdom": "infra-règne",
    "superphylum": "super-embranchement",
    "phylum": "embranchement",
    "subphylum": "sous-embranchement",
    "infraphylum": "infra-embranchement",
    "microphylum": "micro-embranchement",
    "superclass": "super-classe",
    "class": "classe",
    "subclass": "sous-classe",
    "infraclass": "infra-classe",
    "parvclass": "subter-classe",
    "superorder": "super-ordre",
    "order": "ordre",
    "suborder": "sous-ordre",
    "infraorder": "infra-ordre",
    "superfamily": "super-famille",
    "family": "famille",
    "subfamily": "sous-famille",
    "epifamily": "épifamille",
    "tribe": "tribu",
    "subtribe": "sous-tribu",
    "supertribe": "super-tribu",
    "infratribe": "infra-tribu",
    "genus": "genre",
    "subgenus": "sous-genre",
    "species": "espèce",
    "subspecies": "sous-espèce",
    "varietas": "variété",
    "variety": "variété",
    "forma": "forme",
    "form": "forme",
    "section": "section",
    "subsection": "sous-section",
    "series": "série",
    "subseries": "sous-série",
    "cohort": "cohorte",
    "subcohort": "sous-cohorte",
    "supercohort": "super-cohorte",
    "division": "division",
    "subdivision": "sous-division",
    "superdivision": "super-division",
}
"""Ne couvre volontairement pas "kingdom" : ce rang est consommé à part pour struct.regne et
n'apparaît jamais dans struct.rangs (même convention que GBIF, où KINGDOM déclenche un
`continue` plutôt qu'un ajout à la liste des rangs)."""

OTL_KINGDOM_ALIASES: dict[str, str] = {
    "Metazoa": "animal",
    "Chloroplastida": "végétal",
    "Eukaryota": "eucaryote",
    "Bacteria": "bactérie",
    "Archaea": "archaea",
}
"""Noms de nœud kingdom/domain propres à OTL, absents de core.domains.KINGDOM_MAP (qui utilise
les noms GBIF/WoRMS/IRMNG usuels comme "Animalia"/"Plantae"). "Eukaryota" n'est utilisé qu'en
dernier recours (nœud de rang `domain`, pas `kingdom`) quand la lignée ne pose aucun rang
`kingdom` avant la racine — cas réel pour certains groupes de protistes (ex. le clade SAR,
vérifié en direct sur *Plasmodium falciparum*), pas une anomalie à corriger."""


def otl_rang(rank: str) -> str | None:
    return OTL_RANKS.get(rank)


def otl_regne(name: str) -> str | None:
    return KINGDOM_MAP.get(name) or OTL_KINGDOM_ALIASES.get(name)
