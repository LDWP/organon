"""Network access to the Catalogue of Life Extended Release.

Raw HTTP and JSON only, used by `organon.modules.col.module` and
`organon.modules.col_xr.lookup`. `3LXR` is the ChecklistBank alias of
the latest XR release (as `3LR` for the plain COL). The XR merges the
COL with about 17,500 more source checklists and has been the GBIF
default taxonomy since 2024 (alphanumeric ids, distinct from the legacy
GBIF backbone).
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json
from organon.modules.common import checklistbank_children_page, checklistbank_synonyms

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "3LXR"  # latest published XR release (permanent, no discovery)


class ColXrAdapter(OwnedClientMixin):
    """Raw COL XR API client."""

    async def search(self, taxon: str, *, exact: bool = True) -> list[dict]:
        """Search name usages; `exact` restricts to an exact name match.

        Without `exact`, search the scientific name field by relevance;
        see `lookup.resolve_col_xr_matches`, its only caller.
        """
        params: dict[str, str | int] = {
            "limit": 50,
            "offset": 0,
            "q": taxon,
            "status": "_NOT_NULL",
        }
        if exact:
            params["type"] = "EXACT"
            params["sortBy"] = "taxonomic"
        else:
            # `type=EXACT` never matches a name written with a subgenus
            # ("Mus musculus" misses "Mus (Mus) musculus") nor a
            # binomial whose epithet was since corrected (Latin gender
            # agreement). An unfiltered search on a common binomial can
            # return thousands of unrelated results (5043 for
            # "Drosophila melanogaster" sorted by taxonomy), leaving the
            # right record beyond `limit`. Restricting to the scientific
            # name field and sorting by relevance brings it to the top.
            params["sortBy"] = "RELEVANCE"
            params["content"] = "SCIENTIFIC_NAME"
        data = await fetch_json(
            self._client,
            f"{API_BASE}/dataset/{DATASET_ID}/nameusage/search",
            params=params,
            empty_value={},
        )
        return data.get("result", [])

    async def children_page(self, taxon_id: str, offset: int = 0) -> dict:
        """Return a page of children of a taxon."""
        return await checklistbank_children_page(
            self._client, API_BASE, DATASET_ID, taxon_id, offset
        )

    async def synonyms(self, taxon_id: str) -> dict:
        """Return the synonyms of a taxon."""
        return await checklistbank_synonyms(self._client, API_BASE, DATASET_ID, taxon_id)
