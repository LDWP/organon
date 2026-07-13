"""Couche d'accès réseau pour NCBI Taxonomy (E-utilities, eutils.ncbi.nlm.nih.gov) : appels
HTTP et décodage JSON bruts uniquement. Public, sans clé — NCBI recommande un paramètre
`api_key` au-delà de 3 requêtes/seconde, non nécessaire pour l'usage ponctuel de ce module."""

from __future__ import annotations

import httpx

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class NcbiAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_taxid(self, name: str) -> str | None:
        resp = await self._client.get(
            f"{BASE_URL}/esearch.fcgi",
            params={"db": "taxonomy", "term": f"{name}[Scientific Name]", "retmode": "json"},
        )
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
