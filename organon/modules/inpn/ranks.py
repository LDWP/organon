"""TAXREF (INPN) to Wikipedia rank and kingdom tables."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

# TAXREF rank code (`rang.rang` of the JSON API) to Wikipedia rank, from
# the advanced search form. Codes with no clear equivalent in
# `ranks.yaml` are deliberately absent (None) rather than guessed, as
# for GBIF and ITIS: LEG, PVOR, AGES, SMES, MES, NAT, SVAR, FOES, LIN,
# CLO, RACE, MO, AB.
INPN_WP: dict[str, str] = {
    "Dumm": "domaine",
    "SPRG": "super-règne",
    "KD": "règne",
    "SSRG": "sous-règne",
    "IFRG": "infra-règne",
    "PH": "embranchement",
    "SBPH": "sous-embranchement",
    "IFPH": "infra-embranchement",
    "DV": "division",
    "SBDV": "sous-division",
    "SPCL": "super-classe",
    "CLAD": "clade",
    "CL": "classe",
    "SBCL": "sous-classe",
    "IFCL": "infra-classe",
    "PVCL": "subter-classe",
    "SPOR": "super-ordre",
    "COH": "cohorte",
    "OR": "ordre",
    "SBOR": "sous-ordre",
    "IFOR": "infra-ordre",
    "SCO": "section",
    "SSCO": "sous-section",
    "SPFM": "super-famille",
    "FM": "famille",
    "SBFM": "sous-famille",
    "SPTR": "super-tribu",
    "TR": "tribu",
    "SSTR": "sous-tribu",
    "GN": "genre",
    "SSGN": "sous-genre",
    "SC": "section",
    "SBSC": "sous-section",
    "SER": "série",
    "SSER": "sous-série",
    "ES": "espèce",
    "SSES": "sous-espèce",
    "VAR": "variété",
    "FO": "forme",
    "SSFO": "sous-forme",
    "CAR": "cultivar",
}

# The kingdom is stored in struct.kingdom, not duplicated in
# struct.ranks (same as ITIS and GBIF).
KINGDOM_RANKS = {"royaume", "règne"}


def inpn_to_wp_rank(code: str) -> str | None:
    """Return the Wikipedia rank of a TAXREF rank code, or None."""
    return INPN_WP.get(code)


def inpn_lookup_kingdom(kingdom_name: str) -> str:
    """Return the Organon domain of a TAXREF kingdom name."""
    return _SHARED_KINGDOM_MAP.get(kingdom_name, "neutre")
