"""Couche d'accès réseau pour Encyclopedia of Life (eol.org) : appels HTTP et décodage JSON
bruts uniquement. API publique v1/v3, sans clé."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

BASE_URL = "https://eol.org"


class EolAdapter(OwnedClientMixin):
    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/api/search/1.0.json", params={"q": name})
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def page(self, page_id: int) -> dict | None:
        data = await fetch_json(
            self._client,
            f"{BASE_URL}/api/pages/1.0/{page_id}.json",
            params={"common_names": "true", "synonyms": "false", "vetted": "0", "details": "true"},
            empty_value={},
        )
        return data.get("taxonConcept")
