"""Rank table for WFO, from the GraphQL `Rank` enum.

Each node of the chain carries its exact rank, so nothing is deduced.
`code` (the technical root above the kingdom) and `unranked` are
deliberately absent: `wfo_to_wp_rank` returns None, which `module.py`
excludes from the classification. Likewise `prole`, `convar` and `lusus`
(rare infraspecific ranks absent from `ranks.yaml`), rather than
inventing a French label.
"""

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


def wfo_to_wp_rank(rank: str | None) -> str | None:
    """Return the Wikipedia rank of a WFO rank, or None."""
    if not rank:
        return None
    return WFO_RANKS.get(rank.lower())
