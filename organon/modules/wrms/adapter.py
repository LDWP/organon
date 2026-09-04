"""Couche d'accès réseau pour WoRMS : appels HTTP et décodage JSON bruts uniquement, contre
l'API REST documentée sur https://www.marinespecies.org/rest/. La classification structurée en
JSON permet de représenter plusieurs branches sœurs (une classification à sous-familles
multiples, par exemple), et `marine_only` est un paramètre de requête explicite.

`original_description()` est la seule exception à "REST uniquement" : la « publication
originale » n'a aucun champ REST équivalent (vérifié) et reste scrapée depuis la page HTML de
détail (`aphia.php?p=taxdetails`), voir `organon.modules.common.extract_aphia_original_description`
pour l'extraction elle-même (partagée avec IRMNG, même plateforme).

`resolve_doi_citation`/`wikidata_is_edition`/`bhl_*_metadata` sont de simples appels réseau
supplémentaires (mêmes principes que ci-dessus, `resolve_doi_citation` déléguant à
`organon.modules.bibliography`, partagée avec LPSN) utilisés par `organon.modules.wrms.citations`
pour enrichir cette citation brute quand un DOI ou un lien BHL y est repérable — la logique de
décision (quel modèle produire, quand renoncer) vit dans ce module-là, pas ici."""

from __future__ import annotations

import httpx

from organon.core.auth_settings import get_auth_settings
from organon.core.http import USER_AGENT, OwnedClientMixin, fetch_json
from organon.modules.bibliography import WIKIDATA_SPARQL_URL, resolve_doi_citation
from organon.modules.common import extract_aphia_original_description

BASE_URL = "https://www.marinespecies.org/rest"
TAXDETAILS_URL = "https://www.marinespecies.org/aphia.php"
BHL_API_URL = "https://www.biodiversitylibrary.org/api3"


class WrmsAdapter(OwnedClientMixin):
    def __init__(
        self, client: httpx.AsyncClient | None = None, bhl_api_key: str | None = None
    ) -> None:
        super().__init__(client)
        settings = get_auth_settings()
        self._bhl_api_key = bhl_api_key if bhl_api_key is not None else settings.bhl_api_key

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

    async def resolve_doi_citation(self, doi: str) -> str | None:
        return await resolve_doi_citation(self._client, doi)

    async def wikidata_is_edition(self, qid: str) -> bool:
        """Vérifie qu'un item Wikidata est bien une édition (P31=Q3331189) avant de s'en servir
        pour {{Bibliographie|Qxxx}} : appelé avec l'item "œuvre" générique plutôt qu'une édition
        précise, ce modèle produit un rendu incomplet (pas d'ISBN/OCLC, voir sa documentation).
        `qid` doit déjà avoir été validé par l'appelant (motif `Q[1-9][0-9]*`) : interpolé comme
        IRI, pas comme littéral, `sparql_escape` ne s'applique pas ici."""
        query = f"ASK {{ wd:{qid} wdt:P31 wd:Q3331189 }}"
        resp = await self._client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        return bool(resp.json().get("boolean"))

    async def _bhl_get(self, op: str, id_param: str, id_value: str) -> dict | None:
        if not self._bhl_api_key:
            return None
        resp = await self._client.get(
            BHL_API_URL,
            params={"op": op, id_param: id_value, "apikey": self._bhl_api_key, "format": "json"},
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("Result")
        if data.get("Status") != "ok" or not result:
            return None
        return result[0]

    async def bhl_page_metadata(self, page_id: str) -> dict | None:
        return await self._bhl_get("GetPageMetadata", "pageid", page_id)

    async def bhl_item_metadata(self, item_id: str) -> dict | None:
        return await self._bhl_get("GetItemMetadata", "id", item_id)

    async def bhl_title_metadata(self, title_id: str) -> dict | None:
        return await self._bhl_get("GetTitleMetadata", "id", title_id)
