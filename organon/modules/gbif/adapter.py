"""Couche d'accès réseau pour GBIF : appels HTTP et décodage JSON bruts uniquement, aucune
logique métier (voir module.py).
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

BASE_URL = "https://api.gbif.org/v1"
DATASET_KEY = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"  # Backbone Taxonomy GBIF (legacy, ids entiers)


class GbifAdapter(OwnedClientMixin):
    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/species", params={"datasetKey": DATASET_KEY, "name": name}
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def search_any(self, query: str, limit: int = 20) -> list[dict]:
        """Recherche floue sur `species/search` (endpoint distinct de `search()` ci-dessus) :
        matche à la fois sur le nom scientifique et sur les noms vernaculaires, toutes langues
        confondues. Restreint au Backbone Taxonomy (`DATASET_KEY`) pour éviter les doublons
        d'autres checklists indexées par GBIF."""
        resp = await self._client.get(
            f"{BASE_URL}/species/search",
            params={"q": query, "datasetKey": DATASET_KEY, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def name_info(self, key: int) -> dict | None:
        return await fetch_json(self._client, f"{BASE_URL}/species/{key}/name")

    async def species_profiles(self, key: int) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/species/{key}/speciesProfiles")
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def species_record(self, key: int) -> dict | None:
        return await fetch_json(self._client, f"{BASE_URL}/species/{key}")

    async def iucn_red_list_category(self, key: int) -> dict | None:
        return await fetch_json(self._client, f"{BASE_URL}/species/{key}/iucnRedListCategory")

    async def children_page(self, key: int, offset: int = 0) -> dict:
        resp = await self._client.get(f"{BASE_URL}/species/{key}/children", params={"offset": offset})
        resp.raise_for_status()
        return resp.json()

    async def vernacular_names_page(self, key: int, offset: int = 0) -> dict:
        resp = await self._client.get(
            f"{BASE_URL}/species/{key}/vernacularNames", params={"offset": offset}
        )
        resp.raise_for_status()
        return resp.json()

    async def synonyms_page(self, key: int, offset: int = 0) -> dict:
        resp = await self._client.get(f"{BASE_URL}/species/{key}/synonyms", params={"offset": offset})
        resp.raise_for_status()
        return resp.json()
