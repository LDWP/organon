"""Couche d'accès réseau pour Catalogue of Life (checklistbank.org) : appels HTTP et décodage
JSON bruts uniquement.

`3LR` est l'alias ChecklistBank pour la dernière release publiée du projet CoL (dataset n°3,
`alias: "COL"`, `version: "project"` sur `GET /dataset/3`) — utilisé ici en constante, sans
étape de découverte, à l'image de `DATASET_KEY` en dur dans `organon/modules/gbif/adapter.py`.
Interroger le dataset "3" (projet, copie de travail continuellement éditée) au lieu de "3LR"
renvoie des `id` internes à cette copie de travail, différents des identifiants stables publiés
sur catalogueoflife.org/data/taxon/{id} (résolus contre la dernière release, pas le projet)."""

from __future__ import annotations

import httpx

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "3LR"  # dernière release publiée du projet "COL" (permanent, sans découverte)


class ColAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, taxon: str) -> dict | None:
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
            return None
        resp.raise_for_status()
        return resp.json()
