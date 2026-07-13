"""Couche d'accès réseau pour iNaturalist (api.inaturalist.org/v1) : appels HTTP et décodage
JSON bruts uniquement. Un taxon introuvable renvoie 200 avec `results: []` (vérifié en direct,
aussi bien pour une recherche par nom que pour un identifiant inexistant) — pas de statut
d'erreur à intercepter."""

from __future__ import annotations

import httpx

BASE_URL = "https://api.inaturalist.org/v1"


class InaturalistAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/taxa", params={"q": name})
        resp.raise_for_status()
        return resp.json().get("results") or []

    async def taxon(self, taxon_id: int) -> dict | None:
        """Fiche complète d'un taxon, avec `ancestors` (lignée racine -> taxon, rang+nom inclus
        pour chaque nœud) et `names` (tous les noms propres à CE taxon, un par langue/lexique).

        `all_names=true` est utilisé plutôt que `locale=fr` + le champ `preferred_common_name` :
        vérifié en direct que `preferred_common_name` avec `locale=fr` hérite silencieusement
        du nom vernaculaire d'un taxon ANCÊTRE quand le taxon demandé n'a lui-même aucun nom
        français (ex. le coléoptère *Cryptocephalus sericeus*, sans nom français connu, renvoie
        "Animaux" — le nom français du règne Animalia, pas le sien). Le champ `names` de cette
        requête, lui, ne contient que les noms réellement associés à ce taxon précis (confirmé :
        aucune entrée `locale: fr` pour ce même coléoptère avec `all_names=true`)."""
        resp = await self._client.get(f"{BASE_URL}/taxa/{taxon_id}", params={"all_names": "true"})
        resp.raise_for_status()
        results = resp.json().get("results") or []
        return results[0] if results else None
