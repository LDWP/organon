"""Couche d'accès réseau pour Open Tree of Life (api.opentreeoflife.org/v3) : appels HTTP et
décodage JSON bruts uniquement. Deux routes suffisent : `tnrs/match_names` (recherche par nom,
avec résolution de synonyme déjà faite côté serveur) et `taxonomy/taxon_info` (fiche détaillée,
lignée complète via `include_lineage`, ou enfants directs via `include_children`)."""

from __future__ import annotations

import httpx

BASE_URL = "https://api.opentreeoflife.org/v3"


class OtlAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def match_names(self, name: str) -> list[dict]:
        """POST tnrs/match_names : renvoie les correspondances pour un seul nom interrogé
        (`results[0]['matches']`). Un nom inconnu renvoie une liste vide (200, pas d'erreur)."""
        resp = await self._client.post(f"{BASE_URL}/tnrs/match_names", json={"names": [name]})
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return []
        return results[0].get("matches") or []

    async def taxon_info(
        self, ott_id: int, *, include_lineage: bool = False, include_children: bool = False
    ) -> dict | None:
        """POST taxonomy/taxon_info : renvoie None pour un `ott_id` inconnu (l'API répond 400
        avec un corps `{"message": "...Unrecognized OTT ID..."}`, vérifié en direct)."""
        payload: dict = {"ott_id": ott_id}
        if include_lineage:
            payload["include_lineage"] = True
        if include_children:
            payload["include_children"] = True
        resp = await self._client.post(f"{BASE_URL}/taxonomy/taxon_info", json=payload)
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        return resp.json()
