"""Couche d'accès réseau pour CITES via l'API Species+ (speciesplus.net) : appels HTTP et
décodage JSON bruts uniquement."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

BASE_URL = "https://www.speciesplus.net/api/v1"


class CitesAdapter(OwnedClientMixin):
    async def autocomplete(self, name: str) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/auto_complete_taxon_concepts", params={"taxonomy": "cites", "taxon_concept_query": name}
        )
        resp.raise_for_status()
        return resp.json().get("auto_complete_taxon_concepts") or []

    async def taxon_concept(self, concept_id: int) -> dict | None:
        data = await fetch_json(
            self._client, f"{BASE_URL}/taxon_concepts/{concept_id}", empty_value={}
        )
        return data.get("taxon_concept")
