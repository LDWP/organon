"""Table de rangs pour Hesperomys. L'enum GraphQL `Rank` (introspecté sur l'API, voir
adapter.py) mélange rangs taxonomiques standards et rangs de bibliographie nomenclaturale
(ex. `synonym_genus`, `informal_species`, `other_family`) qui ne correspondent à aucun rang
Wikipédia : seuls les rangs standards sont mappés ci-dessous, le reste retombe sur "NOTFOUND"
(même convention que GBIF_WP/ITIS_WP)."""

from __future__ import annotations

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
"""`kingdom`/`superkingdom`/`subkingdom`/`infrakingdom`/`domain`/`root` sont volontairement
mappés (ou omis pour `root`, non atteignable en pratique) mais exclus de la chaîne de rangs
par `_STOP_RANKS` dans adapter.py — le "règne" est stocké séparément dans struct.regne, pas
dupliqué dans struct.rangs (même convention que ITIS, voir RANGS_REGNE dans itis/ranks.py)."""


def hesperomys_cherche_rang(rang: str | None) -> str | None:
    if not rang:
        return None
    return HESPEROMYS_RANKS.get(rang, "NOTFOUND")
