"""Rank table for the Catalogue of Life Extended Release.

Reuses GBIF's rank vocabulary (`GBIF_WP`): same Linnaean ranks, only the
case differs (GBIF constants are uppercase, ChecklistBank strings
lowercase). Completed with ChecklistBank ranks absent from GBIF, the XR
ancestral chain being finer than the legacy backbone's.
"""

from __future__ import annotations

from organon.modules.gbif.ranks import GBIF_WP

COL_XR_RANKS: dict[str, str] = {k.lower(): v for k, v in GBIF_WP.items()} | {
    "parvphylum": "micro-embranchement",
    "megaclass": "super-classe",
    "gigaclass": "super-classe",
    "magnorder": "magnordre",
    "grandorder": "grandordre",
    "parvorder": "micro-ordre",
    "infrafamily": "infra-famille",
    "infragenus": "infra-genre",
    "series": "série",
    "subseries": "sous-série",
}


def col_xr_to_wp_rank(rank: str) -> str | None:
    """Return the Wikipedia rank of a COL XR rank, or None."""
    return COL_XR_RANKS.get(rank)
