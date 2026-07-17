"""Couche d'accès réseau pour AlgaeBase (api2.algaebase.org) : appels HTTP et décodage JSON
bruts uniquement. Aucune clé API publique documentée : le site amorce un cookie de session sur
algaebase.org puis l'échange contre une clé courte-durée sur /auth/, à joindre en en-tête
`abapikey` de chaque appel.

La clé n'est volontairement PAS mise en cache au niveau de l'adaptateur : les instances de
module sont enregistrées une seule fois pour toute la durée de vie du process (voir
`organon.core.registry.register_module`), donc une clé mise en cache indéfiniment risquerait de
devenir périmée pour toutes les requêtes suivantes sans jamais se renouveler. `fetch_key()` est
donc appelé une fois par appel à `collect()`."""

from __future__ import annotations

import httpx

SITE_URL = "https://www.algaebase.org/"
AUTH_URL = "https://api2.algaebase.org/auth/"
API_BASE = "https://api2.algaebase.org/v1.3"

_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.algaebase.org",
    "DNT": "1",
    "Referer": "https://www.algaebase.org/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


class AlgaeBaseAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_key(self) -> str | None:
        """Porte alg_apikey() : amorce le cookie de session puis récupère la clé courte-durée."""
        resp = await self._client.get(SITE_URL)
        if resp.status_code >= 400:
            return None
        resp = await self._client.get(AUTH_URL, headers=_HEADERS)
        if resp.status_code >= 400:
            return None
        key = resp.text.strip()
        return key or None

    async def _get(self, key: str, path: str, params: dict | None = None) -> dict | None:
        headers = {**_HEADERS, "abapikey": key}
        resp = await self._client.get(f"{API_BASE}{path}", params=params, headers=headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def search_genus(self, key: str, genus: str) -> dict | None:
        return await self._get(key, "/genus", params={"genus": genus, "offset": 0, "order": "genus,false"})

    async def genus_detail(self, key: str, taxon_id: int) -> dict | None:
        return await self._get(key, f"/genus/{taxon_id}")

    async def search_species_page(self, key: str, name: str, offset: int = 0) -> dict | None:
        return await self._get(key, "/species", params={"scientificname": name, "offset": offset})

    async def species_detail(self, key: str, taxon_id: int) -> dict | None:
        return await self._get(key, f"/species/{taxon_id}")

    async def search_taxonomy(self, key: str, term: str) -> dict | None:
        return await self._get(key, "/taxonomy", params={"searchTerm": term, "offset": 0})

    async def taxonomy_detail(self, key: str, taxon_id: int) -> dict | None:
        return await self._get(key, f"/taxonomy/{taxon_id}")

    async def taxonomy_page_detail(self, key: str, taxon_id: int) -> dict | None:
        return await self._get(key, f"/taxonomy/{taxon_id}/detail")
