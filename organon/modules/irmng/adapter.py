"""Couche d'accès réseau pour IRMNG (irmng.org/rest) : appels HTTP et décodage JSON bruts
uniquement. IRMNG tourne sur la même plateforme Aphia/VLIZ que WoRMS (cf.
`organon/modules/wrms/`), avec la même forme de réponse — seule différence notable : les routes
et champs JSON utilisent `IRMNG_ID` là où WoRMS utilise `AphiaID` (ex. `AphiaRecordByIRMNG_ID`
et non `AphiaRecordByAphiaID`). Aucune documentation Swagger publique pour ces routes,
contrairement à WoRMS — noms confirmés par appel direct.

`original_description()` est la seule exception à "REST uniquement" : la « publication
originale » n'a aucun champ REST équivalent et reste scrapée depuis la page HTML de détail
(`aphia.php?p=taxdetails`), voir `organon.modules.common.extract_aphia_original_description`
pour l'extraction elle-même (partagée avec WoRMS, même plateforme)."""

from __future__ import annotations

import httpx

from organon.modules.common import extract_aphia_original_description

BASE_URL = "https://www.irmng.org/rest"
TAXDETAILS_URL = "https://www.irmng.org/aphia.php"


class IrmngAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def records_by_name(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/AphiaRecordsByName/{name}", params={"like": "false"})
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def record_by_id(self, irmng_id: int) -> dict | None:
        resp = await self._client.get(f"{BASE_URL}/AphiaRecordByIRMNG_ID/{irmng_id}")
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()

    async def classification_by_id(self, irmng_id: int) -> dict | None:
        resp = await self._client.get(f"{BASE_URL}/AphiaClassificationByIRMNG_ID/{irmng_id}")
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()

    async def children_by_id(self, irmng_id: int, offset: int = 1) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/AphiaChildrenByIRMNG_ID/{irmng_id}", params={"offset": offset}
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def synonyms_by_id(self, irmng_id: int, offset: int = 1) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/AphiaSynonymsByIRMNG_ID/{irmng_id}", params={"offset": offset}
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def vernaculars_by_id(self, irmng_id: int) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/AphiaVernacularsByIRMNG_ID/{irmng_id}")
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json() or []

    async def original_description(self, irmng_id: int) -> str | None:
        resp = await self._client.get(TAXDETAILS_URL, params={"p": "taxdetails", "id": irmng_id})
        if resp.status_code != 200:
            return None
        return extract_aphia_original_description(resp.text)
