"""Couche d'accès réseau pour le World Catalogue of Opiliones (WCO) : appels HTTP et décodage
JSON bruts uniquement, aucune logique métier.

Distribué via ChecklistBank (dataset `2256`, alias « WCO », DOI `10.48580/d4pt`) — même
plateforme et même schéma de réponse que `organon.modules.bryonames.adapter`/`col_xr.adapter`,
seul le dataset diffère. L'interface publique (`wcolite.com`) n'expose aucune API propre : c'est
ChecklistBank qui sert de source de données ici."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "2256"  # alias "WCO" (DOI 10.48580/d4pt), resynchronisé depuis TaxonWorks


class WcoAdapter(OwnedClientMixin):
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
        resp = await self._client.get(
            f"{API_BASE}/dataset/{DATASET_ID}/tree/{taxon_id}/children", params={"offset": offset}
        )
        resp.raise_for_status()
        return resp.json()

    async def synonyms(self, taxon_id: str) -> dict:
        resp = await self._client.get(f"{API_BASE}/dataset/{DATASET_ID}/taxon/{taxon_id}/synonyms")
        resp.raise_for_status()
        return resp.json()
