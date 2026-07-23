"""Couche d'accès réseau pour Hesperomys (https://hesperomys.com) : appels HTTP et décodage
JSON bruts uniquement, aucune logique métier (voir module.py).

L'API GraphQL (`/graphql`) n'est pas documentée publiquement, mais son usage a été confirmé
directement par l'auteur du site en 2024 (voir organon/core/data/db_inventory.yaml, entrée
`hesperomys`) — un export Zenodo statique (dernier connu :
https://zenodo.org/records/10481656) existe en repli, mais l'API en direct est retenue ici :
données à jour, comme les autres modules HTTP directs du dépôt (GBIF, ITIS...). Le schéma exact
des champs utilisés ci-dessous a été retrouvé par introspection GraphQL standard
(`{ __schema { types { ... } } }`), le endpoint l'autorisant.

`taxonByLabel(label: <nom scientifique exact, espace, casse d'origine>)` est le seul point
d'entrée fiable trouvé pour résoudre un nom vers un `Taxon` : il ne matche que les taxons
valides (un nom de synonyme, ex. "Felis leo", renvoie une liste vide — vérifié en direct), donc
aucune logique de suivi de synonyme n'est possible côté Hesperomys (contrairement à
GBIF/ITIS/POWO) - `search()` (plein texte) existe mais indexe surtout les articles
bibliographiques, pas les taxons, et n'est pas utilisé ici.

La chaîne de classification n'est pas exposée en un seul appel : `parent` sur `Taxon` ne
renvoie qu'un niveau. `ancestors()` remonte donc la chaîne par appels successifs (un par rang),
bornée par `_MAX_ANCESTOR_HOPS` pour éviter une boucle si l'API renvoyait un cycle inattendu."""

from __future__ import annotations

import asyncio
import time

import httpx

BASE_URL = "https://hesperomys.com/graphql"

_MIN_INTERVAL = 0.2  # ~5 requêtes/s, prudence par défaut pour une API tierce non documentée
_MAX_ANCESTOR_HOPS = 30
_EXCLUDE_RANKS = {"domain", "superkingdom", "kingdom", "subkingdom", "infrakingdom", "root"}
"""Jamais inclus dans la chaîne : le "règne" est stocké séparément dans struct.regne."""
_CEILING_RANK = "class_"
"""Hesperomys est une base cladistique de paléontologie : au-delà de la classe, la chaîne des
parents continue dans des clades synapsides pré-mammaliens (ex. "Eucynodontia",
"Theriimorpha") sans intérêt pour une taxobox d'espèce actuelle/fossile de mammifère — la
remontée s'arrête donc juste après avoir inclus l'ancêtre de rang "classe" (vérifié en direct
sur Panthera leo : sans cette borne, la chaîne remonte sur ~30 niveaux jusqu'au Trias)."""

_AUTHOR_TAG_FRAGMENT = """
authorTags {
    __typename
    ... on Author {
        person { familyName }
    }
}
"""

_TAXON_BY_LABEL_QUERY = """
query($label: String!) {
    taxonByLabel(label: $label) { oid validName rank }
}
"""

_PARENT_FRAGMENT = f"""
parent {{
    oid
    validName
    rank
    baseName {{ year {_AUTHOR_TAG_FRAGMENT} }}
}}
"""

_TAXON_DETAIL_QUERY = f"""
query($oid: Int!) {{
    taxon(oid: $oid) {{
        oid
        rank
        age
        validName
        {_PARENT_FRAGMENT}
        class_ {{ validName }}
        baseName {{
            oid
            correctedOriginalName
            originalName
            year
            {_AUTHOR_TAG_FRAGMENT}
        }}
        names(first: 100) {{
            edges {{
                node {{
                    oid
                    status
                    originalRank
                    correctedOriginalName
                    originalName
                    rootName
                    year
                    {_AUTHOR_TAG_FRAGMENT}
                }}
            }}
        }}
    }}
}}
"""

_PARENT_QUERY = f"""
query($oid: Int!) {{
    taxon(oid: $oid) {{ {_PARENT_FRAGMENT} }}
}}
"""

_last_call = 0.0
_lock = asyncio.Lock()


async def _throttle() -> None:
    global _last_call
    async with _lock:
        wait = _last_call + _MIN_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


class HesperomysAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _query(self, query: str, variables: dict) -> dict | None:
        await _throttle()
        try:
            resp = await self._client.post(BASE_URL, json={"query": query, "variables": variables})
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        payload = resp.json()
        if "errors" in payload:
            return None
        return payload.get("data")

    async def taxon_by_label(self, label: str) -> list[dict]:
        data = await self._query(_TAXON_BY_LABEL_QUERY, {"label": label})
        if data is None:
            return []
        return data.get("taxonByLabel") or []

    async def taxon_detail(self, oid: int) -> dict | None:
        data = await self._query(_TAXON_DETAIL_QUERY, {"oid": oid})
        if data is None:
            return None
        return data.get("taxon")

    async def ancestors(self, first_parent: dict | None) -> list[dict]:
        """Remonte la chaîne des taxons parents à partir du premier parent déjà connu (issu de
        `taxon_detail()`), un appel réseau par niveau supplémentaire. S'arrête faute de parent,
        sur `_EXCLUDE_RANKS`, ou juste après avoir inclus `_CEILING_RANK` (voir sa docstring)."""
        chain: list[dict] = []
        current = first_parent
        hops = 0
        while current is not None and hops < _MAX_ANCESTOR_HOPS:
            rank = current.get("rank")
            if rank in _EXCLUDE_RANKS:
                break
            chain.append(current)
            if rank == _CEILING_RANK:
                break
            data = await self._query(_PARENT_QUERY, {"oid": current["oid"]})
            if data is None or data.get("taxon") is None:
                break
            current = data["taxon"].get("parent")
            hops += 1
        return chain
