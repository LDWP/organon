"""Utilitaires réseau partagés entre les adaptateurs de modules (organon.modules.*), pour
éviter de dupliquer le cycle de vie du client HTTP et le motif garde-statut-vide + décodage
JSON dans chaque adapter.py."""

from __future__ import annotations

from typing import Any

import httpx


class OwnedClientMixin:
    """Gère un `httpx.AsyncClient` optionnellement injecté (tests, partage entre adaptateurs)
    ou créé et possédé par l'adaptateur lui-même (usage normal) : `aclose()` ne ferme le
    client que si l'adaptateur l'a créé, jamais un client fourni par l'appelant."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=follow_redirects
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    empty_statuses: tuple[int, ...] = (404,),
    empty_value: Any = None,
) -> Any:
    """GET + décodage JSON, avec repli sur `empty_value` pour les statuts listés dans
    `empty_statuses` (ex. 404/204 = ressource absente, pas une erreur) avant
    `raise_for_status()`."""
    resp = await client.get(url, params=params, headers=headers)
    if resp.status_code in empty_statuses:
        return empty_value
    resp.raise_for_status()
    return resp.json()
