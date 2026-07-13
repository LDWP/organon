"""Couche d'accès réseau pour Encyclopedia of Life (eol.org) : appels HTTP et décodage JSON
bruts uniquement. API publique v1/v3, sans clé."""

from __future__ import annotations

import httpx

BASE_URL = "https://eol.org"


class EolAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/api/search/1.0.json", params={"q": name})
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def page(self, page_id: int) -> dict | None:
        resp = await self._client.get(
            f"{BASE_URL}/api/pages/1.0/{page_id}.json",
            params={"common_names": "true", "synonyms": "false", "vetted": "0", "details": "true"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("taxonConcept")
