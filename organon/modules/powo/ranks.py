"""Table de rangs pour POWO (Plants of the World Online / WCVP). Les rangs POWO sont observés
en majuscules (ex. "SPECIES") sauf pour "Form" dans certaines listes de synonymes — la
correspondance est donc faite insensible à la casse."""

from __future__ import annotations

POWO_RANKS: dict[str, str] = {
    "KINGDOM": "règne",
    "PHYLUM": "embranchement",
    "CLASS": "classe",
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


def powo_cherche_rang(rang: str | None) -> str | None:
    if not rang:
        return None
    return POWO_RANKS.get(rang.upper())
