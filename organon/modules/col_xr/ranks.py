"""Table de rangs pour la Catalogue of Life Extended Release (ChecklistBank, dataset 3LXR).

Réutilise le vocabulaire de rangs de GBIF (`GBIF_WP`) plutôt que de dupliquer à la main une
cinquantaine de libellés français identiques : ce sont les mêmes rangs linnéens, seule la casse
diffère (GBIF : constantes MAJUSCULES : ChecklistBank : chaînes minuscules). Complété par les
quelques rangs propres à ChecklistBank absents du vocabulaire GBIF — la chaîne ancestrale de la
XR est nettement plus fine que celle du backbone legacy, qui n'expose que les 6-7 rangs
linnéens standards (ex. "parvphylum"/"megaclass" observés en pratique sur des taxons animaux)."""

from __future__ import annotations

from organon.modules.gbif.ranks import GBIF_WP

COL_XR_RANKS: dict[str, str] = {k.lower(): v for k, v in GBIF_WP.items() if k != "NOTFOUND"} | {
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


def col_xr_cherche_rang(rang: str) -> str:
    return COL_XR_RANKS.get(rang, "non classé")
