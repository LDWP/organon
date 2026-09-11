"""Table de rangs pour WFO (World Flora Online).

Contrairement à POWO, ni la page de recherche ni la fiche détail n'exposent un rang par
ancêtre de la chaîne de classification (`#taxonHierarchy`, voir `adapter.ancestors`) : seuls
le nom et l'auteur de chaque nœud y figurent. Le rang de chaque ancêtre est donc déduit :

- pour famille et au-dessus, par la terminaison latine imposée par le Code international de
  nomenclature pour les algues, les champignons et les plantes (ICN, art. 16-19) : -phyta
  (embranchement), -opsida (classe), -idae (sous-classe), -ales (ordre), -aceae (famille),
  etc. Vérifié sur la chaîne réelle de plusieurs taxons (ex. Marchantiophyta/Jungermanniopsida/
  Jungermanniidae/Frullaniales/Frullaniaceae) — aucune source WFO ne fournit ce rang
  directement, contrairement au champ `rank` de POWO.
- pour genre et espèce (rangs sans terminaison standardisée), par correspondance positionnelle
  avec le nom du taxon demandé : le genre est le premier mot du nom scientifique, l'espèce les
  deux premiers pour un taxon infraspécifique — une certitude nomenclaturale, pas une
  supposition.

« Angiosperms » (`wfo-9949999999`) est un cas à part : nœud de statut Accepted, rang phylum
côté backbone WFO (vérifié sur le téléchargement 2026-06 du backbone), mais sans terminaison
standard ni auteur — reconnu par son identifiant plutôt que par suffixe. « Plantae »
(`wfo-4100001250`, le règne racine de toute la chaîne) est traité de la même façon."""

from __future__ import annotations

WFO_RANKS: dict[str, str] = {
    "KINGDOM": "règne",
    "PHYLUM": "embranchement",
    "CLASS": "classe",
    "SUBCLASS": "sous-classe",
    "ORDER": "ordre",
    "SUBORDER": "sous-ordre",
    "FAMILY": "famille",
    "SUBFAMILY": "sous-famille",
    "TRIBE": "tribu",
    "SUBTRIBE": "sous-tribu",
    "GENUS": "genre",
    "SUBGENUS": "sous-genre",
    "SECTION": "section",
    "SUBSECTION": "sous-section",
    "SERIES": "série",
    "SUBSERIES": "sous-série",
    "SPECIES": "espèce",
    "SUBSPECIES": "sous-espèce",
    "VARIETY": "variété",
    "SUBVARIETY": "sous-variété",
    "FORM": "forme",
    "SUBFORM": "sous-forme",
}


def wfo_cherche_rang(rang: str | None) -> str | None:
    """Mappe le champ `Rank:` d'un résultat `/search` (rang du taxon lui-même, ex. "Variety")
    vers le libellé français interne."""
    if not rang:
        return None
    return WFO_RANKS.get(rang.upper())


_SUFFIX_RANKS: list[tuple[str, str]] = [
    ("oideae", "sous-famille"),
    ("aceae", "famille"),
    ("ineae", "sous-ordre"),
    ("anae", "super-ordre"),
    ("ales", "ordre"),
    ("inae", "sous-tribu"),
    ("eae", "tribu"),
    ("idae", "sous-classe"),
    ("opsida", "classe"),
    ("phytina", "sous-embranchement"),
    ("phyta", "embranchement"),
]
"""Ordre du plus spécifique au plus générique : plusieurs terminaisons se recouvrent
(-oideae/-aceae/-ineae se terminent aussi par -eae ; -aceae par -eae) — la première
correspondance dans cet ordre l'emporte."""

_SPECIAL_ANCESTOR_RANKS: dict[str, str] = {
    "wfo-9949999999": "embranchement",  # "Angiosperms" — Accepted, rang phylum côté backbone
    "wfo-4100001250": "règne",  # "Plantae" — racine de la chaîne, sans terminaison de rang
}


def wfo_cherche_rang_ancetre(wfo_id: str, nom: str, taxon_nom: str) -> str | None:
    """Déduit le rang d'un ancêtre de la chaîne de classification (voir docstring du module).
    `taxon_nom` = nom du taxon demandé, pour la correspondance positionnelle genre/espèce."""
    special = _SPECIAL_ANCESTOR_RANKS.get(wfo_id)
    if special:
        return special
    for suffix, rang in _SUFFIX_RANKS:
        if nom.endswith(suffix):
            return rang
    taxon_mots = taxon_nom.split()
    if nom == " ".join(taxon_mots[:1]) and len(taxon_mots) > 1:
        return "genre"
    if nom == " ".join(taxon_mots[:2]) and len(taxon_mots) > 2:
        return "espèce"
    return None
