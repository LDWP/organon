"""Couche d'accès réseau pour GRIN Taxonomy : appels HTTP et décodage JSON bruts uniquement,
aucune logique métier.

`npgsweb.ars-grin.gov` a été écarté par sondage direct (ASP.NET WebForms classique, résolution
nom→id uniquement par formulaire de recherche POST avec `__VIEWSTATE`/`__EVENTVALIDATION` à
renouveler à chaque requête — scraping stateful fragile, voir `organon/core/data/db_inventory.yaml`,
entrée `grin`) ; les données sont cependant distribuées sans restriction via ChecklistBank — même
plateforme et même schéma de réponse que `organon.modules.bryonames.adapter`, seul le dataset
diffère."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "2018"  # GRIN Taxonomy, resynchronisé depuis npgsweb.ars-grin.gov (2026-08-30)


class GrinAdapter(OwnedClientMixin):
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
