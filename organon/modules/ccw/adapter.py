"""Couche d'accès réseau pour la Checklist of the Collembola of the World (CCW) : appels HTTP et
décodage JSON bruts uniquement, aucune logique métier.

Distribué via ChecklistBank (dataset `2130`, alias « Collembola.org », DOI `10.48580/d4kh`) —
même plateforme et même schéma de réponse que `organon.modules.wco.adapter`/`bryonames.adapter`,
seul le dataset diffère."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json
from organon.modules.common import checklistbank_children_page, checklistbank_synonyms

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "2130"  # alias "Collembola.org" (DOI 10.48580/d4kh), version Feb 2025


class CcwAdapter(OwnedClientMixin):
    async def search(self, taxon: str) -> list[dict]:
        data = await fetch_json(
            self._client,
            f"{API_BASE}/dataset/{DATASET_ID}/nameusage/search",
            params={
                "limit": 50,
                "offset": 0,
                "q": taxon,
                "sortBy": "taxonomic",
                "status": "_NOT_NULL",
                "type": "EXACT",
            },
            empty_value={},
        )
        return data.get("result", [])

    async def children_page(self, taxon_id: str, offset: int = 0) -> dict:
        return await checklistbank_children_page(
            self._client, API_BASE, DATASET_ID, taxon_id, offset
        )

    async def synonyms(self, taxon_id: str) -> dict:
        return await checklistbank_synonyms(self._client, API_BASE, DATASET_ID, taxon_id)
