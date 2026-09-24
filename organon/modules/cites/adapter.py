"""Network access to CITES through the Species+ API (speciesplus.net).

Raw HTTP and JSON only.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

BASE_URL = "https://www.speciesplus.net/api/v1"


class CitesAdapter(OwnedClientMixin):
    """Raw Species+ client."""

    async def autocomplete(self, name: str) -> list[dict]:
        """Return the taxon concepts matching a name."""
        resp = await self._client.get(
            f"{BASE_URL}/auto_complete_taxon_concepts",
            params={"taxonomy": "cites", "taxon_concept_query": name},
        )
        resp.raise_for_status()
        return resp.json().get("auto_complete_taxon_concepts") or []

    async def taxon_concept(self, concept_id: int) -> dict | None:
        """Return a taxon concept by id, or None."""
        data = await fetch_json(
            self._client, f"{BASE_URL}/taxon_concepts/{concept_id}", empty_value={}
        )
        return data.get("taxon_concept")
