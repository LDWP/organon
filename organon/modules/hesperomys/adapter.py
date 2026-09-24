"""Network access to Hesperomys (https://hesperomys.com).

Raw HTTP and JSON only; see module.py.

The GraphQL API (`/graphql`) is not publicly documented, but its use was
confirmed by the site's author in 2024 (see `db_inventory.yaml`). The
live API is preferred to the static Zenodo export: up-to-date data. The
fields used were found by standard GraphQL introspection.

`taxonByLabel(label: <exact scientific name>)` is the only reliable
entry point to resolve a name to a `Taxon`. It matches only valid taxa
(a synonym returns an empty list), so synonyms cannot be followed.
`search()` mostly indexes bibliographic articles, not taxa.

The chain is not exposed in one call: `parent` returns one level, so
`ancestors()` climbs by successive calls, bounded by
`_MAX_ANCESTOR_HOPS` against an unexpected cycle.
"""

from __future__ import annotations

import logging

import httpx

from organon.core.http import MinIntervalThrottle, OwnedClientMixin

logger = logging.getLogger(__name__)

BASE_URL = "https://hesperomys.com/graphql"

_MIN_INTERVAL = 0.2  # ~5 requests/s, cautious for an undocumented third-party API
_MAX_ANCESTOR_HOPS = 30
# Never included in the chain: the kingdom is stored in struct.kingdom.
_EXCLUDE_RANKS = {"domain", "superkingdom", "kingdom", "subkingdom", "infrakingdom", "root"}
# Hesperomys is a cladistic paleontology database: above the class the
# chain goes on into pre-mammalian synapsid clades, useless for a mammal
# taxobox. The climb stops right after the class ancestor (for Panthera
# leo it would otherwise go ~30 levels up to the Triassic).
_CEILING_RANK = "class_"

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

_throttle = MinIntervalThrottle(_MIN_INTERVAL).wait


class HesperomysAdapter(OwnedClientMixin):
    """Raw Hesperomys GraphQL client."""

    async def _query(self, query: str, variables: dict) -> dict | None:
        """Run a GraphQL query; return its data, or None on error."""
        await _throttle()
        try:
            resp = await self._client.post(BASE_URL, json={"query": query, "variables": variables})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Hesperomys injoignable (%s)", exc)
            return None
        payload = resp.json()
        if "errors" in payload:
            logger.warning("Hesperomys : erreurs GraphQL (%s)", payload["errors"])
            return None
        return payload.get("data")

    async def taxon_by_label(self, label: str) -> list[dict]:
        """Return the taxa whose label matches."""
        data = await self._query(_TAXON_BY_LABEL_QUERY, {"label": label})
        if data is None:
            return []
        return data.get("taxonByLabel") or []

    async def taxon_detail(self, oid: int) -> dict | None:
        """Return the detail of a taxon id, or None."""
        data = await self._query(_TAXON_DETAIL_QUERY, {"oid": oid})
        if data is None:
            return None
        return data.get("taxon")

    async def ancestors(self, first_parent: dict | None) -> list[dict]:
        """Climb the parent chain from the first known parent.

        One network call per extra level. Stops without parent, on
        `_EXCLUDE_RANKS`, or right after including `_CEILING_RANK`.
        """
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
