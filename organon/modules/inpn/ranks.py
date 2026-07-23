"""Tables de correspondance de rangs/règnes TAXREF (INPN) -> Wikipédia."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP as _SHARED_KINGDOM_MAP

# Code de rang TAXREF (champ `rang.rang` de l'API JSON) -> rang Wikipédia. Liste exhaustive
# extraite du formulaire de recherche avancée (`<select name="rang.rang">` sur
# https://taxref.mnhn.fr/taxref-web/taxa/search) le 2026-07-23. Les codes sans équivalent
# clair dans `core/data/ranks.yaml` sont volontairement absents (résolus en "NOTFOUND" par
# `inpn_cherche_rang`) plutôt que rapprochés au jugé — même convention que GBIF/ITIS : LEG
# (legio), PVOR (parv-ordre), AGES (agrégat), SMES (semi-espèce), MES (micro-espèce), NAT
# (natio), SVAR (sous-variété), FOES (forma species), LIN (linea), CLO (clône), RACE (race),
# MO (morpha), AB (abberatio).
INPN_WP: dict[str, str] = {
    "Dumm": "domaine", "SPRG": "super-règne", "KD": "règne", "SSRG": "sous-règne",
    "IFRG": "infra-règne", "PH": "embranchement", "SBPH": "sous-embranchement",
    "IFPH": "infra-embranchement", "DV": "division", "SBDV": "sous-division",
    "SPCL": "super-classe", "CLAD": "clade", "CL": "classe", "SBCL": "sous-classe",
    "IFCL": "infra-classe", "PVCL": "subter-classe", "SPOR": "super-ordre", "COH": "cohorte",
    "OR": "ordre", "SBOR": "sous-ordre", "IFOR": "infra-ordre", "SCO": "section",
    "SSCO": "sous-section", "SPFM": "super-famille", "FM": "famille", "SBFM": "sous-famille",
    "SPTR": "super-tribu", "TR": "tribu", "SSTR": "sous-tribu", "GN": "genre",
    "SSGN": "sous-genre", "SC": "section", "SBSC": "sous-section", "SER": "série",
    "SSER": "sous-série", "ES": "espèce", "SSES": "sous-espèce", "VAR": "variété",
    "FO": "forme", "SSFO": "sous-forme", "CAR": "cultivar",
}

# Le "règne" est stocké séparément dans struct.regne, pas dupliqué dans struct.rangs — même
# convention que ITIS/GBIF.
RANGS_REGNE = {"royaume", "règne"}


def inpn_cherche_rang(code: str) -> str:
    return INPN_WP.get(code, "NOTFOUND")


def inpn_cherche_regne(nom_regne: str) -> str:
    return _SHARED_KINGDOM_MAP.get(nom_regne, "neutre")
