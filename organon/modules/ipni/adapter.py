"""Network access to IPNI (ipni.org/api/1): raw HTTP and JSON only.

The only useful route is `search`, whose answer mixes name, publication
and author records (`recordType`). Only name records have a `name` field
(see module.py: the exact-match filter drops the other two).

`resolve_doi_citation` delegates to `organon.modules.bibliography`,
shared with WoRMS and LPSN; see `organon.modules.ipni.citations`.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin
from organon.modules.bibliography import resolve_doi_citation

BASE_URL = "https://www.ipni.org/api/1"


class IpniAdapter(OwnedClientMixin):
    """Raw IPNI API client."""

    async def search(self, name: str) -> list[dict]:
        """Return the IPNI records matching a name."""
        resp = await self._client.get(f"{BASE_URL}/search", params={"q": name, "perPage": 50})
        resp.raise_for_status()
        return resp.json().get("results") or []

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation."""
        return await resolve_doi_citation(self._client, doi)
