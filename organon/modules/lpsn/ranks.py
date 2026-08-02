"""Tables de correspondance de rangs/domaines LPSN -> Wikipédia.

LPSN suit le Code international de nomenclature des procaryotes (ICNP), dont la hiérarchie
officielle de rangs est nettement plus courte que celle des codes zoologique/botanique : pas de
sous-embranchement, super-famille, tribu, etc. `LPSN_WP` couvre donc uniquement les valeurs de
`category` réellement définies par l'ICNP (domain, kingdom, phylum, class, order, family, genus,
species, subspecies — "kingdom" est un ajout récent, 2021-2022, encore rare en pratique).

"phylum" est gardé tel quel (pas traduit en "embranchement") : c'est le mot utilisé aussi bien
par l'ICNP que par le paramètre `rang` du modèle Wikipédia {{LPSN}} (voir `module.py`), et
`organon/core/data/ranks.yaml` le liste comme rang autonome distinct de "embranchement" pour
cette raison."""

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

# "domain" (Bacteria/Archaea) est le niveau équivalent à struct.regne pour ce module (comme
# "Kingdom" pour ITIS/GBIF) : `module.py` arrête la remontée de la chaîne des parents dès qu'il
# atteint ce niveau, sans l'ajouter à struct.rangs, pour ne pas dupliquer l'info déjà portée par
# struct.regne. "kingdom" (rang ICNP réellement distinct, ex. Bacillati) reste lui inclus dans la
# chaîne.


def lpsn_cherche_rang(category: str | None) -> str:
    if not category:
        return "NOTFOUND"
    return LPSN_WP.get(category, "NOTFOUND")


def lpsn_cherche_regne(domain_name: str | None) -> str:
    """`domain_name` = `full_name` du nœud LPSN de catégorie "domain" (ex. "Bacteria",
    "Archaea"). Réutilise la table partagée plutôt qu'une copie : LPSN n'a pas de cas
    particulier comme le Chromista d'ITIS."""
    if not domain_name:
        return ""
    return _SHARED_KINGDOM_MAP.get(domain_name, "")
