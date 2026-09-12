"""Couche d'accès réseau pour ZooBank : appels HTTP et décodage JSON bruts uniquement, aucune
logique métier.

`zoobank.org` lui-même est derrière une vérification anti-robot avec reCAPTCHA (testé en
direct : bandeau "Human User Verification" sur toute page, y compris `/Api`) ; les données sont
cependant distribuées sans restriction via ChecklistBank — même plateforme et même schéma de
réponse que `organon.modules.col_xr.adapter`/`organon.modules.bryonames.adapter`, seul le
dataset diffère. Une seule route utile ici : `search` (pas de `children`/`synonyms`, voir
module.py pour le motif — ce dataset n'est pas traité comme une classification)."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "2037"  # alias "ZooBank DwCA" (DOI 10.48580/d4g9), resynchronisé 2026-08-31


class ZoobankAdapter(OwnedClientMixin):
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
