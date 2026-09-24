"""Network access to science.mnhn.fr (Muséum national).

A simple existence check of a taxon page by HTTP code, with no data
extraction: the site has no structured API for these pages, only HTML
pages of which only the existence (200 vs 404) is used.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin

BASE_URL = "https://science.mnhn.fr/taxon"


class MnhnAdapter(OwnedClientMixin):
    """Raw MNHN client."""

    async def exists(self, path: str) -> bool:
        """Return True if the taxon page exists."""
        resp = await self._client.get(f"{BASE_URL}/{path}")
        return resp.status_code == 200
