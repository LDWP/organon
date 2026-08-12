"""Couche d'accès réseau pour WoRMS : appels HTTP et décodage JSON bruts uniquement, contre
l'API REST documentée sur https://www.marinespecies.org/rest/. La classification structurée en
JSON permet de représenter plusieurs branches sœurs (une classification à sous-familles
multiples, par exemple), et `marine_only` est un paramètre de requête explicite.

`original_description()` est la seule exception à "REST uniquement" : la « publication
originale » n'a aucun champ REST équivalent (vérifié) et reste scrapée depuis la page HTML de
détail (`aphia.php?p=taxdetails`), voir `organon.modules.common.extract_aphia_original_description`
pour l'extraction elle-même (partagée avec IRMNG, même plateforme)."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json
from organon.modules.common import extract_aphia_original_description

BASE_URL = "https://www.marinespecies.org/rest"
TAXDETAILS_URL = "https://www.marinespecies.org/aphia.php"


class WrmsAdapter(OwnedClientMixin):
    async def records_by_name(self, name: str, marine_only: bool = False) -> list[dict]:
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaRecordsByName/{name}",
            params={"like": "false", "marine_only": "true" if marine_only else "false"},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def record_by_id(self, aphia_id: int) -> dict | None:
        return await fetch_json(
            self._client, f"{BASE_URL}/AphiaRecordByAphiaID/{aphia_id}", empty_statuses=(204,)
        )

    async def classification_by_id(self, aphia_id: int) -> dict | None:
        return await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaClassificationByAphiaID/{aphia_id}",
            empty_statuses=(204,),
        )

    async def children_by_id(self, aphia_id: int, marine_only: bool = False, offset: int = 1) -> list[dict]:
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaChildrenByAphiaID/{aphia_id}",
            params={"marine_only": "true" if marine_only else "false", "offset": offset},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def synonyms_by_id(self, aphia_id: int, offset: int = 1) -> list[dict]:
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaSynonymsByAphiaID/{aphia_id}",
            params={"offset": offset},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def vernaculars_by_id(self, aphia_id: int) -> list[dict]:
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaVernacularsByAphiaID/{aphia_id}",
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def original_description(self, aphia_id: int) -> str | None:
        resp = await self._client.get(TAXDETAILS_URL, params={"p": "taxdetails", "id": aphia_id})
        if resp.status_code != 200:
            return None
        return extract_aphia_original_description(resp.text)
