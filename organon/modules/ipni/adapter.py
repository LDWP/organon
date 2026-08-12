"""Couche d'accès réseau pour IPNI (ipni.org/api/1) : appels HTTP et décodage JSON bruts
uniquement. Une seule route utile ici : `search`, qui mélange dans une même réponse des
enregistrements de nom, de publication et d'auteur (`recordType`) — seuls les enregistrements
de nom portent un champ `name` (voir module.py pour le filtrage par correspondance exacte, qui
élimine les deux autres types au passage)."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin

BASE_URL = "https://www.ipni.org/api/1"


class IpniAdapter(OwnedClientMixin):
    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(f"{BASE_URL}/search", params={"q": name, "perPage": 50})
        resp.raise_for_status()
        return resp.json().get("results") or []
