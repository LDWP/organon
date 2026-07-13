"""Couche d'accès réseau pour Tropicos (tropicos.org/api) : appels HTTP et décodage JSON bruts
uniquement.

Le jeton ci-dessous est le jeton public utilisé par le widget de recherche du site lui-même
côté client (pas un jeton personnel). Comme tout jeton non documenté officiellement par
Tropicos, il peut être révoqué/changé sans préavis côté site — dans ce cas le module échouera
proprement (statut HTTP non 200) plutôt que silencieusement."""

from __future__ import annotations

import httpx

BASE_URL = "https://www.tropicos.org/api"
_TOKEN = "RjRGNDA4RDgtOEY2NS00NzVGLUI3NDktRjk4MjE2Q0NCRTQ1"


class TropicosAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        headers = {
            "Authorization": f"Bearer {_TOKEN}",
            "Referer": "https://www.tropicos.org/name/Search",
        }
        self._client = client or httpx.AsyncClient(timeout=30.0, headers=headers)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/Search/NameLookup",
            params={"value": name, "returnCount": 10, "lookupType": 1},
        )
        resp.raise_for_status()
        return resp.json() or []
