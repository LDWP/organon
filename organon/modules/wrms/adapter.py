"""Couche d'accès réseau pour WoRMS : appels HTTP et décodage JSON bruts uniquement, contre
l'API REST documentée sur https://www.marinespecies.org/rest/. La classification structurée en
JSON permet de représenter plusieurs branches sœurs (une classification à sous-familles
multiples, par exemple), et `marine_only` est un paramètre de requête explicite.

`original_description()` est la seule exception à "REST uniquement" : la « publication
originale » n'a aucun champ REST équivalent (vérifié) et reste scrapée depuis la page HTML de
détail (`aphia.php?p=taxdetails`), voir `organon.modules.common.extract_aphia_original_description`
pour l'extraction elle-même (partagée avec IRMNG, même plateforme)."""

from __future__ import annotations

import httpx

from organon.modules.common import extract_aphia_original_description

BASE_URL = "https://www.marinespecies.org/rest"
TAXDETAILS_URL = "https://www.marinespecies.org/aphia.php"


class WrmsAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def records_by_name(self, name: str, marine_only: bool = False) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/AphiaRecordsByName/{name}",
            params={"like": "false", "marine_only": "true" if marine_only else "false"},
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def record_by_id(self, aphia_id: int) -> dict | None:
        resp = await self._client.get(f"{BASE_URL}/AphiaRecordByAphiaID/{aphia_id}")
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()

    async def classification_by_id(self, aphia_id: int) -> dict | None:
        resp = await self._client.get(f"{BASE_URL}/AphiaClassificationByAphiaID/{aphia_id}")
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()

    async def children_by_id(self, aphia_id: int, marine_only: bool = False, offset: int = 1) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/AphiaChildrenByAphiaID/{aphia_id}",
            params={"marine_only": "true" if marine_only else "false", "offset": offset},
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def synonyms_by_id(self, aphia_id: int, offset: int = 1) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/AphiaSynonymsByAphiaID/{aphia_id}", params={"offset": offset}
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def vernaculars_by_id(self, aphia_id: int) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/AphiaVernacularsByAphiaID/{aphia_id}")
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def original_description(self, aphia_id: int) -> str | None:
        resp = await self._client.get(TAXDETAILS_URL, params={"p": "taxdetails", "id": aphia_id})
        if resp.status_code != 200:
            return None
        return extract_aphia_original_description(resp.text)
