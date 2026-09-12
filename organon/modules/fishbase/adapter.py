"""Couche d'accès réseau pour FishBase : appels HTTP et décodage JSON bruts uniquement, aucune
logique métier.

`fishbase.org`/`fishbase.se` eux-mêmes n'offrent aucune API stable (scraping HTML fragile,
endpoint jamais porté — voir `docs/md/db-inventory.md`) ; les données sont cependant distribuées
sans restriction via ChecklistBank — même plateforme et même schéma de réponse que
`organon.modules.bryonames.adapter`/`organon.modules.col.adapter`, seul le dataset diffère.
Depuis le 2025-05-01, cet export COLDP est généré depuis la plateforme Aphia/VLIZ (même backend
que WoRMS/IRMNG) : les identifiants sont donc des LSID WoRMS (`urn:lsid:marinespecies.org:...`),
pas les codes numériques natifs FishBase (SpecCode/FamCode) — voir le docstring de `module.py`
pour l'effet sur le rendu Bioref."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "1010"  # alias "WoRMS FishBase", resynchronisé 2026-09-02 (108155 enregistrements)


class FishbaseAdapter(OwnedClientMixin):
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
