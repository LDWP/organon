"""Rank table for POWO (Plants of the World Online / WCVP).

Ranks are seen in uppercase ("SPECIES"), except "Form" in some synonym
lists, so matching is case-insensitive.
"""

from __future__ import annotations

POWO_RANKS: dict[str, str] = {
    "KINGDOM": "règne",
    "PHYLUM": "embranchement",
    "CLASS": "classe",
    "SUBCLASS": "sous-classe",
    "ORDER": "ordre",
    "FAMILY": "famille",
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
    "FORM": "forme",
    "FORMA": "forme",
}


def powo_to_wp_rank(rank: str | None) -> str | None:
    """Return the Wikipedia rank of a POWO rank, or None."""
    if not rank:
        return None
    return POWO_RANKS.get(rank.upper())


# WCVP only covers Plantae, so a one-entry table is enough.
POWO_KINGDOM_MAP: dict[str, str] = {"Plantae": "végétal"}


def powo_lookup_kingdom(kingdom: str | None) -> str | None:
    """Return the Organon domain of a POWO kingdom, or None."""
    if not kingdom:
        return None
    return POWO_KINGDOM_MAP.get(kingdom)
