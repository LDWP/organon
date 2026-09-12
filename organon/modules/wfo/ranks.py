"""Table de rangs pour WFO. Alimentée par l'enum GraphQL `Rank` de
`https://list.worldfloraonline.org/gql.php` (voir `adapter.py`) : contrairement à
worldfloraonline.org (aucun rang exposé par ancêtre), chaque nœud de la chaîne de classification
porte directement son rang exact — aucune déduction nécessaire.

`code` (nœud technique racine de toute chaîne, au-dessus du règne) et `unranked` sont
délibérément absents de cette table plutôt que mappés vers un rang français inexistant :
`wfo_cherche_rang` renvoie `None`, que `module.py` traite comme "à exclure de la classification"
plutôt que comme une erreur. Idem pour `prole`/`convar`/`lusus` (rangs infraspécifiques rares,
absents de `core/data/ranks.yaml`) : laissés non traduits plutôt que d'inventer un libellé
français qu'aucune autre source du dépôt n'utilise."""

from __future__ import annotations

WFO_RANKS: dict[str, str] = {
    "kingdom": "règne",
    "subkingdom": "sous-règne",
    "phylum": "embranchement",
    "class": "classe",
    "subclass": "sous-classe",
    "superorder": "super-ordre",
    "order": "ordre",
    "suborder": "sous-ordre",
    "family": "famille",
    "subfamily": "sous-famille",
    "supertribe": "super-tribu",
    "tribe": "tribu",
    "subtribe": "sous-tribu",
    "genus": "genre",
    "subgenus": "sous-genre",
    "section": "section",
    "subsection": "sous-section",
    "series": "série",
    "subseries": "sous-série",
    "species": "espèce",
    "subspecies": "sous-espèce",
    "variety": "variété",
    "subvariety": "sous-variété",
    "form": "forme",
    "subform": "sous-forme",
}


def wfo_cherche_rang(rang: str | None) -> str | None:
    if not rang:
        return None
    return WFO_RANKS.get(rang.lower())
