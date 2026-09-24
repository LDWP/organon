"""Network access to VASCAN (data.canadensys.net/vascan/api/0.1).

Raw HTTP and JSON only. The one useful route is `search`, which returns
a list of results per searched term (`results[0]['matches']`); an
unknown name gives `numMatches: 0` with an absent or empty `matches`
list (200, no error).
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin

BASE_URL = "https://data.canadensys.net/vascan/api/0.1"


class VascanAdapter(OwnedClientMixin):
    """Raw VASCAN client."""

    async def search(self, name: str) -> list[dict]:
        """Return the matches for a name."""
        resp = await self._client.get(f"{BASE_URL}/search.json", params={"q": name})
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return []
        return results[0].get("matches") or []
