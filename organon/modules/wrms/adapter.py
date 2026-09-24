"""Network access to WoRMS: raw HTTP and JSON against the REST API.

The structured JSON classification can hold several sister branches, and
`marine_only` is an explicit query parameter.

`original_description()` is the one exception to "REST only": the
original publication has no REST field and is scraped from the HTML
detail page; see `organon.modules.common.
extract_aphia_original_description`, shared with IRMNG.

`resolve_doi_citation`, `wikidata_is_edition` and `bhl_*_metadata` are
extra network calls used by `organon.modules.wrms.citations` to enrich
that raw citation; the decision logic lives there.
"""

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
    """Raw WoRMS API client."""

    def __init__(
        self, client: httpx.AsyncClient | None = None, bhl_api_key: str | None = None
    ) -> None:
        """Use `client` and the BHL key if given, else the defaults."""
        super().__init__(client)
        settings = get_auth_settings()
        self._bhl_api_key = bhl_api_key if bhl_api_key is not None else settings.bhl_api_key

    async def records_by_name(self, name: str, marine_only: bool = False) -> list[dict]:
        """Return the Aphia records matching `name` exactly."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaRecordsByName/{name}",
            params={"like": "false", "marine_only": "true" if marine_only else "false"},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def record_by_id(self, aphia_id: int) -> dict | None:
        """Return the Aphia record of an id, or None."""
        return await fetch_json(
            self._client, f"{BASE_URL}/AphiaRecordByAphiaID/{aphia_id}", empty_statuses=(204,)
        )

    async def classification_by_id(self, aphia_id: int) -> dict | None:
        """Return the nested classification of an id, or None."""
        return await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaClassificationByAphiaID/{aphia_id}",
            empty_statuses=(204,),
        )

    async def children_by_id(
        self, aphia_id: int, marine_only: bool = False, offset: int = 1
    ) -> list[dict]:
        """Return a page of children of an id."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaChildrenByAphiaID/{aphia_id}",
            params={"marine_only": "true" if marine_only else "false", "offset": offset},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def synonyms_by_id(self, aphia_id: int, offset: int = 1) -> list[dict]:
        """Return a page of synonyms of an id."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaSynonymsByAphiaID/{aphia_id}",
            params={"offset": offset},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def vernaculars_by_id(self, aphia_id: int) -> list[dict]:
        """Return the vernacular names of an id."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaVernacularsByAphiaID/{aphia_id}",
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def original_description(self, aphia_id: int) -> str | None:
        """Return the original description scraped from the page."""
        resp = await self._client.get(TAXDETAILS_URL, params={"p": "taxdetails", "id": aphia_id})
        if resp.status_code != 200:
            return None
        return extract_aphia_original_description(resp.text)

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation."""
        return await resolve_doi_citation(self._client, doi)

    async def wikidata_is_edition(self, qid: str) -> bool:
        """Return True if a Wikidata item is an edition (P31=Q3331189).

        Checked before using it for {{Bibliographie|Qxxx}}: with the
        generic "work" item the template renders incompletely (no ISBN
        or OCLC). `qid` must already be validated (`Q[1-9][0-9]*`): it
        is interpolated as an IRI, not a literal, so `sparql_escape`
        does not apply.
        """
        query = f"ASK {{ wd:{qid} wdt:P31 wd:Q3331189 }}"
        resp = await self._client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        return bool(resp.json().get("boolean"))

    async def _bhl_get(self, op: str, id_param: str, id_value: str) -> dict | None:
        """Call a BHL operation; return its first result."""
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
        """Return the BHL metadata of a page."""
        return await self._bhl_get("GetPageMetadata", "pageid", page_id)

    async def bhl_item_metadata(self, item_id: str) -> dict | None:
        """Return the BHL metadata of an item."""
        return await self._bhl_get("GetItemMetadata", "id", item_id)

    async def bhl_title_metadata(self, title_id: str) -> dict | None:
        """Return the BHL metadata of a title."""
        return await self._bhl_get("GetTitleMetadata", "id", title_id)
