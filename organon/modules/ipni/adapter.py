"""Couche d'accès réseau pour IPNI (ipni.org/api/1) : appels HTTP et décodage JSON bruts
uniquement. Une seule route utile ici : `search`, qui mélange dans une même réponse des
enregistrements de nom, de publication et d'auteur (`recordType`) — seuls les enregistrements
de nom portent un champ `name` (voir module.py pour le filtrage par correspondance exacte, qui
élimine les deux autres types au passage)."""

from __future__ import annotations

import httpx

BASE_URL = "https://www.ipni.org/api/1"


class IpniAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/search", params={"q": name, "perPage": 50})
        resp.raise_for_status()
        return resp.json().get("results") or []
