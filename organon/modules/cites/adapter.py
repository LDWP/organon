"""Couche d'accès réseau pour CITES via l'API Species+ (speciesplus.net) : appels HTTP et
décodage JSON bruts uniquement."""

from __future__ import annotations

import httpx

BASE_URL = "https://www.speciesplus.net/api/v1"


class CitesAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def autocomplete(self, name: str) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/auto_complete_taxon_concepts", params={"taxonomy": "cites", "taxon_concept_query": name}
        )
        resp.raise_for_status()
        return resp.json().get("auto_complete_taxon_concepts") or []

    async def taxon_concept(self, concept_id: int) -> dict | None:
        resp = await self._client.get(f"{BASE_URL}/taxon_concepts/{concept_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("taxon_concept")
