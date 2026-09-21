"""Couche d'accès réseau pour la classification COI/IOC (« IOC World Bird List ») : appels HTTP
et décodage JSON bruts uniquement, aucune logique métier.

`worldbirdnames.org` a été restructuré (vérifié en direct : les anciennes pages par famille
`/Family/<Nom>` renvoient 404, remplacées par un site de contenu WordPress sans fiche par taxon
navigable) et n'expose aucune API propre. Les données sont cependant distribuées sans
restriction via ChecklistBank — même plateforme et même schéma de réponse que
`organon.modules.bryonames.adapter`/`wco.adapter`, seul le dataset diffère.

Pas de méthode `synonyms()` ici, contrairement à ces modules : ce dataset ne porte que des noms
acceptés (vérifié en direct sur l'API, voir `module.py`), `/taxon/<id>/synonyms` y renvoie
toujours un objet vide."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "2036"  # alias "IOC" (DOI 10.48580/d4g8), resynchronisé depuis worldbirdnames.org


class CoiIocAdapter(OwnedClientMixin):
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
