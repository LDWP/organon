"""Network access to AlgaeBase (api2.algaebase.org): raw HTTP and JSON.

No public API key is documented: the site primes a session cookie on
algaebase.org, then exchanges it for a short-lived key on /auth/, sent
in the `abapikey` header of each call.

The key is deliberately NOT cached in the adapter: module instances are
registered once for the process lifetime (see
`organon.core.registry.register_module`), so a key cached forever would
go stale for all later requests. `fetch_key()` is called once per
`collect()`.
"""

from __future__ import annotations

import httpx

from organon.core.http import MinIntervalThrottle, OwnedClientMixin, fetch_json
from organon.modules.bibliography import resolve_doi_citation

SITE_URL = "https://www.algaebase.org/"
AUTH_URL = "https://api2.algaebase.org/auth/"
API_BASE = "https://api2.algaebase.org/v1.3"

_throttle = MinIntervalThrottle(0.2).wait

_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.algaebase.org",
    "DNT": "1",
    "Referer": "https://www.algaebase.org/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


class AlgaeBaseAdapter(OwnedClientMixin):
    """Raw AlgaeBase API client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, throttle=_throttle)

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation (see bibliography)."""
        return await resolve_doi_citation(self._client, doi)

    async def fetch_key(self) -> str | None:
        """Prime the session cookie and fetch the API key."""
        resp = await self._client.get(SITE_URL)
        if resp.status_code >= 400:
            return None
        resp = await self._client.get(AUTH_URL, headers=_HEADERS)
        if resp.status_code >= 400:
            return None
        key = resp.text.strip()
        return key or None

    async def _get(self, key: str, path: str, params: dict | None = None) -> dict | None:
        """GET an API path with the key."""
        headers = {**_HEADERS, "abapikey": key}
        return await fetch_json(self._client, f"{API_BASE}{path}", params=params, headers=headers)

    async def search_genus(self, key: str, genus: str) -> dict | None:
        """Search genera by name."""
        return await self._get(
            key, "/genus", params={"genus": genus, "offset": 0, "order": "genus,false"}
        )

    async def genus_detail(self, key: str, taxon_id: int) -> dict | None:
        """Return the detail of a genus id."""
        return await self._get(key, f"/genus/{taxon_id}")

    async def search_species_page(self, key: str, name: str, offset: int = 0) -> dict | None:
        """Return a page of species search results."""
        return await self._get(key, "/species", params={"scientificname": name, "offset": offset})

    async def species_detail(self, key: str, taxon_id: int) -> dict | None:
        """Return the detail of a species id."""
        return await self._get(key, f"/species/{taxon_id}")

    async def search_taxonomy(self, key: str, term: str) -> dict | None:
        """Search higher taxa by term."""
        return await self._get(key, "/taxonomy", params={"searchTerm": term, "offset": 0})

    async def taxonomy_detail(self, key: str, taxon_id: int) -> dict | None:
        """Return the detail of a taxonomy id."""
        return await self._get(key, f"/taxonomy/{taxon_id}")

    async def taxonomy_page_detail(self, key: str, taxon_id: int) -> dict | None:
        """Return the detail page of a taxonomy id."""
        return await self._get(key, f"/taxonomy/{taxon_id}/detail")
