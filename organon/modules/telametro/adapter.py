"""Couche d'accès réseau pour Tela Botanica / TelaMétro (référentiel BDTFX, flore de France
métropolitaine) : appels HTTP contre l'index Algolia `Flore` que le site utilise lui-même pour
sa recherche, et scraping HTML de l'onglet « Ethnobotanique » de la fiche eFlore pour les noms
vernaculaires typés. La clé `x-algolia-api-key` ci-dessous est une clé Algolia "search-only"
(lecture seule, publique par construction — visible dans le JavaScript client du site), pas un
secret.

Les noms vernaculaires renvoyés par l'index Algolia (`bdtfx.common_name`) sont une liste plate
sans indication de statut ni de langue, et son contenu ne correspond à aucun sous-ensemble
cohérent de la table complète (ex. pour Quercus robur, il omet « Chêne à grappes » et
« Chêne femelle », tous deux classés « Secondaire ou régional »). Cette table complète, avec son
« Conseil d'emploi » par nom (Recommandé ou typique / Secondaire ou régional / Peu usité et à
éviter), n'existe dans aucune API JSON documentée — seule la page HTML server-rendue de l'onglet
Ethnobotanique l'expose (`<table class="liste_noms_vernaculaires">`), d'où le scraping ici plutôt
qu'un appel structuré."""

from __future__ import annotations

import html
import re

from organon.core.http import OwnedClientMixin

ALGOLIA_URL = "https://yotvbfebjc-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_PARAMS = {
    "x-algolia-agent": "Algolia for vanilla JavaScript (lite) 3.24.5",
    "x-algolia-application-id": "YOTVBFEBJC",
    "x-algolia-api-key": "843a36372facc0f1836f53d1d5968aa8",
}

ETHNOBOTANIQUE_URL = "https://www.tela-botanica.org/eflore/"

_LIGNE_VERNACULAIRE_RE = re.compile(
    r"<tr>\s*<td>(?P<langue>[^<]*)</td>\s*<td>(?P<nom>[^<]*)</td>\s*<td>[^<]*</td>\s*"
    r"<td>(?P<statut>[^<]*)</td>\s*<td>[^<]*</td>\s*</tr>"
)
_STATUTS_RETENUS = frozenset({"Recommandé ou typique", "Secondaire ou régional"})
"""« Peu usité et à éviter » est délibérément exclu : la BDTFX déconseille elle-même ces noms,
les inclure irait à l'encontre du signal éditorial de la source."""


class TelametroAdapter(OwnedClientMixin):
    async def search(self, name: str) -> list[dict]:
        params = (
            f"query={name}&hitsPerPage=20&maxValuesPerFacet=10&page=0"
            f"&facetFilters=%5B%22referentiels%3Abdtfx%22%5D&facets=%5B%22referentiels%22%5D&tagFilters="
        )
        payload = {"requests": [{"indexName": "Flore", "params": params}]}
        resp = await self._client.post(ALGOLIA_URL, params=ALGOLIA_PARAMS, json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0].get("hits", []) if results else []

    async def noms_communs_fr(self, num_nom: int) -> dict[str, list[str]]:
        """Noms vernaculaires français de la fiche `num_nom`, groupés par statut
        (« Recommandé ou typique » / « Secondaire ou régional » — voir `_STATUTS_RETENUS`),
        dans l'ordre d'apparition, dédoublonnés par statut. Un statut absent de la fiche n'a pas
        de clé dans le résultat (pas de liste vide). Résultat entièrement vide si la fiche n'a
        aucun nom vernaculaire référencé (pas une erreur : état normal de la BDTFX)."""
        params = {
            "referentiel": "bdtfx",
            "module": "fiche",
            "num_nom": str(num_nom),
            "onglet": "ethnobotanique",
        }
        resp = await self._client.get(ETHNOBOTANIQUE_URL, params=params)
        resp.raise_for_status()

        noms: dict[str, list[str]] = {}
        for m in _LIGNE_VERNACULAIRE_RE.finditer(resp.text):
            statut = m["statut"].strip()
            if m["langue"].strip() != "fra" or statut not in _STATUTS_RETENUS:
                continue
            nom = html.unescape(m["nom"]).strip()
            if not nom:
                continue
            groupe = noms.setdefault(statut, [])
            if nom not in groupe:
                groupe.append(nom)
        return noms
