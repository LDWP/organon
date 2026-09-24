"""LPSN to Wikipedia rank and domain tables.

LPSN follows the ICNP, whose rank hierarchy is shorter than the
zoological or botanical ones, so `LPSN_WP` only covers the ICNP
`category` values. "phylum" is kept as is: ICNP and the {{LPSN}}
template both use it, and `ranks.yaml` lists it apart.
"""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

LPSN_WP: dict[str, str] = {
    "domain": "domaine",
    "kingdom": "règne",
    "phylum": "phylum",
    "class": "classe",
    "order": "ordre",
    "family": "famille",
    "genus": "genre",
    "species": "espèce",
    "subspecies": "sous-espèce",
}

# "domain" (Bacteria/Archaea) is the equivalent of struct.kingdom here:
# `module.py` stops climbing the parent chain at that level without
# adding it to struct.ranks. "kingdom" (a distinct ICNP rank, e.g.
# Bacillati) stays in the chain.


def lpsn_to_wp_rank(category: str | None) -> str | None:
    """Return the Wikipedia rank of an LPSN category, or None."""
    if not category:
        return None
    return LPSN_WP.get(category)


def lpsn_lookup_kingdom(domain_name: str | None) -> str:
    """Return the kingdom of a domain node name ("Bacteria", "Archaea").

    Reuses the shared table; LPSN has no special case.
    """
    if not domain_name:
        return ""
    return _SHARED_KINGDOM_MAP.get(domain_name, "")
