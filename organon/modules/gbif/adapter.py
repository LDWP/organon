"""Network access to GBIF: raw HTTP and JSON only.

No business logic; see module.py.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json
from organon.modules.bibliography import resolve_doi_citation

BASE_URL = "https://api.gbif.org/v1"
DATASET_KEY = (
    "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"  # GBIF Backbone Taxonomy (legacy, integer ids)
)
TAXREF_DATASET_KEY = "0e61f8fe-7d25-4f81-ada7-d970bbb2c6d6"  # TAXREF (MNHN), a GBIF checklist


class GbifAdapter(OwnedClientMixin):
    """Raw GBIF API client."""

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation (see bibliography)."""
        return await resolve_doi_citation(self._client, doi)

    async def search(self, name: str) -> list[dict]:
        """Return the Backbone species matching `name` exactly."""
        resp = await self._client.get(
            f"{BASE_URL}/species", params={"datasetKey": DATASET_KEY, "name": name}
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def search_any(self, query: str, limit: int = 20) -> list[dict]:
        """Fuzzy search on `species/search` by any name.

        Matches scientific and vernacular names in any language.
        Restricted to the Backbone Taxonomy to avoid duplicates from
        other checklists.
        """
        resp = await self._client.get(
            f"{BASE_URL}/species/search",
            params={"q": query, "datasetKey": DATASET_KEY, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def name_info(self, key: int) -> dict | None:
        """Return the parsed name of a species key, or None."""
        return await fetch_json(self._client, f"{BASE_URL}/species/{key}/name")

    async def species_profiles(self, key: int) -> list[dict]:
        """Return the species profiles of a key."""
        resp = await self._client.get(f"{BASE_URL}/species/{key}/speciesProfiles")
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def species_record(self, key: int) -> dict | None:
        """Return the species record of a key, or None."""
        return await fetch_json(self._client, f"{BASE_URL}/species/{key}")

    async def children_page(self, key: int, offset: int = 0) -> dict:
        """Return a page of children of a key."""
        resp = await self._client.get(
            f"{BASE_URL}/species/{key}/children", params={"offset": offset}
        )
        resp.raise_for_status()
        return resp.json()

    async def vernacular_names_page(self, key: int, offset: int = 0) -> dict:
        """Return a page of vernacular names of a key."""
        resp = await self._client.get(
            f"{BASE_URL}/species/{key}/vernacularNames", params={"offset": offset}
        )
        resp.raise_for_status()
        return resp.json()

    async def synonyms_page(self, key: int, offset: int = 0) -> dict:
        """Return a page of synonyms of a key."""
        resp = await self._client.get(
            f"{BASE_URL}/species/{key}/synonyms", params={"offset": offset}
        )
        resp.raise_for_status()
        return resp.json()

    async def taxref_related(self, key: int) -> list[dict]:
        """Return the TAXREF records of the same taxonomic concept.

        Independent of the existence of a French vernacular name.
        """
        resp = await self._client.get(
            f"{BASE_URL}/species/{key}/related", params={"datasetKey": TAXREF_DATASET_KEY}
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
