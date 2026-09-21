"""Couche d'accès réseau pour GTDB (Genome Taxonomy Database) : appels HTTP et décodage JSON
bruts uniquement, aucune logique métier.

Les URLs d'API directe devinées (`api.gtdb.ecogenomic.org`) restent injoignables/404 (voir
`organon/core/data/db_inventory.yaml`, entrée `gtdb`) ; les données du dataset officiel sont
cependant distribuées sans restriction via ChecklistBank — même plateforme et même schéma de
réponse que `organon.modules.bryonames.adapter`, seul le dataset diffère."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "2214"  # alias "GTDB" (DOI 10.48580/d4nd), resynchronisé à chaque release (r232)


class GtdbAdapter(OwnedClientMixin):
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
