"""Index Fungorum to Wikipedia rank table, and the Fungi kingdom.

The service exposes the rank only as a bibliographic abbreviation
(`INFRASPECIFIC_RANK`, e.g. "sp.", "fam."), which despite its name is
used for ALL ranks. Only abbreviations seen are covered; an unknown one
gives None.

The classification chain (`struct.ranks`) comes from a fixed ladder
joined by `NameByKey` through the taxon's genus, only for genus rank and
below: a family record or above carries none of these fields, which
`module.py` treats as insufficient data (None), not an error. "Incertae
sedis" marks an unresolved intermediate rank and is omitted like an
empty value.
"""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP

IXF_RANKS: dict[str, str] = {
    "regn.": "règne",
    "subregn.": "sous-règne",
    "phyl.": "embranchement",
    "subphyl.": "sous-embranchement",
    "class.": "classe",
    "subclass.": "sous-classe",
    "ord.": "ordre",
    "fam.": "famille",
    "gen.": "genre",
    "sp.": "espèce",
    "subsp.": "sous-espèce",
    "var.": "variété",
    "f.": "forme",
}

# Fields returned by NameByKey for the chain, nearest first.
# Kingdom_name is handled apart (`struct.kingdom` via ixf_kingdom),
# never added to struct.ranks.
CLASSIFICATION_LADDER: list[tuple[str, str]] = [
    ("Genus_name", "genre"),
    ("Family_name", "famille"),
    ("Order_name", "ordre"),
    ("Subclass_name", "sous-classe"),
    ("Class_name", "classe"),
    ("Subphylum_name", "sous-embranchement"),
    ("Phylum_name", "embranchement"),
]

UNRESOLVED_PLACEHOLDER = "Incertae sedis"


def indexfungorum_to_wp_rank(code: str | None) -> str | None:
    """Return the Wikipedia rank of an abbreviation, or None."""
    if not code:
        return None
    return IXF_RANKS.get(code)


def ixf_kingdom(kingdom_name: str | None) -> str | None:
    """Return the Organon domain of a kingdom name, or None."""
    if not kingdom_name:
        return None
    return KINGDOM_MAP.get(kingdom_name, "champignon")
