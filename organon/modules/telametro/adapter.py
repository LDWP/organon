"""Couche d'accès réseau pour Tela Botanica / TelaMétro (référentiel BDTFX, flore de France
métropolitaine) : appels HTTP et décodage JSON bruts uniquement, contre l'index Algolia
`Flore` que le site utilise lui-même pour sa recherche. La clé `x-algolia-api-key` ci-dessous
est une clé Algolia "search-only" (lecture seule, publique par construction — visible dans le
JavaScript client du site), pas un secret."""

from __future__ import annotations

import httpx

ALGOLIA_URL = "https://yotvbfebjc-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_PARAMS = {
    "x-algolia-agent": "Algolia for vanilla JavaScript (lite) 3.24.5",
    "x-algolia-application-id": "YOTVBFEBJC",
    "x-algolia-api-key": "843a36372facc0f1836f53d1d5968aa8",
}


class TelametroAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

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
