"""Couche d'accès réseau pour science.mnhn.fr (Muséum national d'Histoire naturelle) : simple
vérification d'existence d'une fiche taxon par code HTTP, aucune extraction de données —
science.mnhn.fr n'expose aucune API structurée pour ces fiches, seulement des pages HTML dont
seule l'existence (200 vs 404) est exploitée ici."""

from __future__ import annotations

import httpx

BASE_URL = "https://science.mnhn.fr/taxon"


class MnhnAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def exists(self, path: str) -> bool:
        resp = await self._client.get(f"{BASE_URL}/{path}")
        return resp.status_code == 200
