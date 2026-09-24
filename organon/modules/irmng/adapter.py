"""Network access to IRMNG (irmng.org/rest): raw HTTP and JSON only.

IRMNG runs on the same Aphia/VLIZ platform as WoRMS (see
`organon/modules/wrms/`) with the same response shape; the routes and
JSON fields use `IRMNG_ID` where WoRMS uses `AphiaID` (e.g.
`AphiaRecordByIRMNG_ID`). There is no public Swagger documentation for
these routes; names were confirmed by direct calls.

`original_description()` is the one exception to "REST only": the
original publication has no REST field and is scraped from the HTML
detail page; see `organon.modules.common.
extract_aphia_original_description`, shared with WoRMS.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json
from organon.modules.bibliography import resolve_doi_citation
from organon.modules.common import extract_aphia_original_description

BASE_URL = "https://www.irmng.org/rest"
TAXDETAILS_URL = "https://www.irmng.org/aphia.php"


class IrmngAdapter(OwnedClientMixin):
    """Raw IRMNG API client."""

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation (see bibliography)."""
        return await resolve_doi_citation(self._client, doi)

    async def records_by_name(self, name: str) -> list[dict]:
        """Return the records matching `name` exactly."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaRecordsByName/{name}",
            params={"like": "false"},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def record_by_id(self, irmng_id: int) -> dict | None:
        """Return the record of an IRMNG id, or None."""
        return await fetch_json(
            self._client, f"{BASE_URL}/AphiaRecordByIRMNG_ID/{irmng_id}", empty_statuses=(204,)
        )

    async def classification_by_id(self, irmng_id: int) -> dict | None:
        """Return the nested classification of an id, or None."""
        return await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaClassificationByIRMNG_ID/{irmng_id}",
            empty_statuses=(204,),
        )

    async def children_by_id(self, irmng_id: int, offset: int = 1) -> list[dict]:
        """Return a page of children of an id."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaChildrenByIRMNG_ID/{irmng_id}",
            params={"offset": offset},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def synonyms_by_id(self, irmng_id: int, offset: int = 1) -> list[dict]:
        """Return a page of synonyms of an id."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaSynonymsByIRMNG_ID/{irmng_id}",
            params={"offset": offset},
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def vernaculars_by_id(self, irmng_id: int) -> list[dict]:
        """Return the vernacular names of an id."""
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/AphiaVernacularsByIRMNG_ID/{irmng_id}",
            empty_statuses=(204,),
            empty_value=[],
        )
        return data or []

    async def original_description(self, irmng_id: int) -> str | None:
        """Return the original description scraped from the page."""
        resp = await self._client.get(TAXDETAILS_URL, params={"p": "taxdetails", "id": irmng_id})
        if resp.status_code != 200:
            return None
        return extract_aphia_original_description(resp.text)
