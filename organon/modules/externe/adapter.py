"""Couche d'accès réseau pour les liens transversaux Wikimédia (Wikidata/Commons/Wikispecies/
Wiktionnaire) : appels HTTP et décodage JSON bruts uniquement.

Existence de page (Commons/Wikispecies/Wiktionnaire) : utilise l'API MediaWiki standard
(`action=query`) — une page manquante renvoie `pageid: -1` avec une clé `missing`, une page
existante un `pageid` positif sans cette clé (vérifié en direct sur les deux cas).

Le service de requêtes Wikidata (WDQS) applique sa politique de User-Agent (voir
[Wikimedia User-Agent policy](https://meta.wikimedia.org/wiki/User-Agent_policy)) : une requête
sans en-tête descriptif est rejetée en 403 (vérifié en direct)."""

from __future__ import annotations

import httpx

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
SPECIES_API_URL = "https://species.wikimedia.org/w/api.php"
FRWIKTIONARY_API_URL = "https://fr.wiktionary.org/w/api.php"
USER_AGENT = "Organon/0.1 (https://fr.wikipedia.org/wiki/Projet:Biologie/Taxobot)"


class ExterneAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT})
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def wikidata_qid(self, taxon: str) -> str | None:
        """Cherche l'item Wikidata représentant un taxon (P31=taxon, P225=nom scientifique)."""
        query = (
            'SELECT ?item WHERE { ?item wdt:P31 wd:Q16521 ; wdt:P225 "%s" . }' % taxon.replace('"', '\\"')
        )
        resp = await self._client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        uri = bindings[0]["item"]["value"]
        return uri.rsplit("/", 1)[-1]

    async def _page_exists(self, api_url: str, title: str) -> bool:
        resp = await self._client.get(api_url, params={"action": "query", "titles": title, "format": "json"})
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        return any("missing" not in page for page in pages.values())

    async def commons_page_exists(self, title: str) -> bool:
        return await self._page_exists(COMMONS_API_URL, title)

    async def commons_category_exists(self, title: str) -> bool:
        return await self._page_exists(COMMONS_API_URL, f"Category:{title}")

    async def species_page_exists(self, title: str) -> bool:
        return await self._page_exists(SPECIES_API_URL, title)

    async def frwiktionary_page_exists(self, title: str) -> bool:
        return await self._page_exists(FRWIKTIONARY_API_URL, title)
