"""Adaptateur Wikidata : résolution d'un taxon vers son item (QID) via le service de requêtes
WDQS. Politique de User-Agent Wikimédia (voir meta.wikimedia.org/wiki/User-Agent_policy) : une
requête sans en-tête descriptif est rejetée en 403 (vérifié en direct)."""

from __future__ import annotations

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.modules.common import sparql_escape

SPARQL_URL = "https://query.wikidata.org/sparql"


class WikidataAdapter(OwnedClientMixin):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def qid(self, taxon: str) -> str | None:
        """Cherche l'item Wikidata représentant un taxon (P31=taxon, P225=nom scientifique)."""
        nom = sparql_escape(taxon)
        query = f'SELECT ?item WHERE {{ ?item wdt:P31 wd:Q16521 ; wdt:P225 "{nom}" . }}'
        resp = await self._client.get(
            SPARQL_URL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        uri = bindings[0]["item"]["value"]
        return uri.rsplit("/", 1)[-1]
