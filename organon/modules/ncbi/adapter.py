"""Network access to NCBI Taxonomy (E-utilities).

Raw HTTP and JSON only. Public, no key: NCBI recommends an `api_key`
beyond 3 requests per second, unnecessary for this module's occasional
use.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class NcbiAdapter(OwnedClientMixin):
    """Raw NCBI E-utilities client."""

    async def search_taxid(self, name: str) -> str | None:
        """Return the first taxonomy id matching a scientific name."""
        resp = await self._client.get(
            f"{BASE_URL}/esearch.fcgi",
            params={"db": "taxonomy", "term": f"{name}[Scientific Name]", "retmode": "json"},
        )
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
