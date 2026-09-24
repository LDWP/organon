"""ICTV to Wikipedia rank table.

Keys are the columns of `organon/core/data/ictv_taxonomy.tsv`.
`Subkingdom` has no entry: fully empty in the current MSL; add it when
ICTV uses it.

`Realm` and `Subrealm` are deliberately not translated: per
{{Modèle:Taxoboxoutils rang}} on frwiki they show in English through
{{lang|en|Realm}}, linked to [[Realm (virologie)]]; see the `lang_en`
field of `RankEntry` (`core/rendering/grammar.py`).
"""

from __future__ import annotations

_ICTV_RANKS: dict[str, str] = {
    "Realm": "realm",
    "Subrealm": "subrealm",
    "Kingdom": "kingdom",
    "Phylum": "phylum",
    "Subphylum": "sous-phylum",
    "Class": "classe",
    "Subclass": "sous-classe",
    "Order": "ordre",
    "Suborder": "sous-ordre",
    "Family": "famille",
    "Subfamily": "sous-famille",
    "Genus": "genre",
    "Subgenus": "sous-genre",
    "Species": "espèce",
}


def ictv_to_wp_rank(column: str) -> str | None:
    """Return the Wikipedia rank of an ICTV column, or None."""
    return _ICTV_RANKS.get(column)
