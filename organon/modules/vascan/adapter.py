"""Couche d'accès réseau pour VASCAN (data.canadensys.net/vascan/api/0.1) : appels HTTP et
décodage JSON bruts uniquement. Une seule route utile : `search`, qui renvoie une liste de
résultats par terme recherché (`results[0]['matches']`) — un nom introuvable renvoie
`numMatches: 0` avec une liste `matches` absente ou vide (200, pas d'erreur)."""

from __future__ import annotations

import httpx

BASE_URL = "https://data.canadensys.net/vascan/api/0.1"


class VascanAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/search.json", params={"q": name})
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return []
        return results[0].get("matches") or []
