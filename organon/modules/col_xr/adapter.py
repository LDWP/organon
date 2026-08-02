"""Couche d'accès réseau pour la Catalogue of Life Extended Release (ChecklistBank) : appels
HTTP et décodage JSON bruts uniquement, aucune logique métier (voir module.py).

`3LXR` est l'alias ChecklistBank pour la dernière release XR publiée (comme `3LR` pour la COL
classique côté `organon/modules/col/adapter.py`, même infrastructure) — la XR fusionne la COL
avec ~17 500 checklists sources supplémentaires et sert de taxonomie par défaut à GBIF depuis
2024 (ids alphanumériques distincts du backbone GBIF legacy, voir
`organon/modules/gbif/adapter.py`)."""

from __future__ import annotations

import httpx

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "3LXR"  # dernière release XR publiée (permanente, sans découverte)


class ColXrAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, taxon: str) -> list[dict]:
        resp = await self._client.get(
            f"{API_BASE}/dataset/{DATASET_ID}/nameusage/search",
            params={
                "limit": 50,
                "offset": 0,
                "q": taxon,
                "sortBy": "taxonomic",
                "status": "_NOT_NULL",
                "type": "EXACT",
            },
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("result", [])

    async def children_page(self, taxon_id: str, offset: int = 0) -> dict:
        resp = await self._client.get(
            f"{API_BASE}/dataset/{DATASET_ID}/tree/{taxon_id}/children", params={"offset": offset}
        )
        resp.raise_for_status()
        return resp.json()

    async def synonyms(self, taxon_id: str) -> dict:
        resp = await self._client.get(f"{API_BASE}/dataset/{DATASET_ID}/taxon/{taxon_id}/synonyms")
        resp.raise_for_status()
        return resp.json()
