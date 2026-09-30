"""Wikidata adapter: resolve a taxon to its item (QID) through WDQS.

Wikimedia's User-Agent policy: a request without a descriptive header is
rejected with a 403.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.modules.common import sparql_escape

SPARQL_URL = "https://query.wikidata.org/sparql"
# WDQS sometimes answers beyond 10 s (ReadTimeout on simple queries).
_TIMEOUT = 30.0
_ATTEMPTS = 3
# Batch resolution: a single retry, the diagnosis must not wait 3 x 30 s
# more.
_BATCH_ATTEMPTS = 2
# Names per VALUES query: keeps the GET URL under a few KB and the query
# far from the WDQS timeout.
_BATCH_MAX = 50
# taxon, monotypic taxon, fossil taxon, clade; see
# docs/md/wikidata-conventions.md
_TAXON_CLASSES = ("Q16521", "Q310890", "Q23038290", "Q713623")


class WikidataSparqlAdapter(OwnedClientMixin):
    """WDQS SPARQL client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT})

    async def qids(self, taxon: str) -> list[str]:
        """Return all items representing a taxon.

        P31 is one of `_TAXON_CLASSES` and P225 the scientific name.
        Several if the name is a cross-kingdom homonym.
        """
        name = sparql_escape(taxon)
        classes = " ".join(f"wd:{c}" for c in _TAXON_CLASSES)
        query = (
            f"SELECT DISTINCT ?item WHERE {{ VALUES ?classe {{ {classes} }} "
            f'?item wdt:P31 ?classe ; wdt:P225 "{name}" . }}'
        )
        bindings = await self._select(query, _ATTEMPTS)
        return [b["item"]["value"].rsplit("/", 1)[-1] for b in bindings]

    async def taxon_qids(self, names: Iterable[str]) -> dict[str, list[str]]:
        """Return the taxon items of each name, in VALUES batches.

        Every requested name is a key: an empty list if it has no item,
        several if it is a homonym (the adapter does not choose).
        """
        unique = list(dict.fromkeys(names))
        found: dict[str, list[str]] = {n: [] for n in unique}
        classes = " ".join(f"wd:{c}" for c in _TAXON_CLASSES)
        for start in range(0, len(unique), _BATCH_MAX):
            values = " ".join(f'"{sparql_escape(n)}"' for n in unique[start : start + _BATCH_MAX])
            query = (
                f"SELECT DISTINCT ?nom ?item WHERE {{ VALUES ?classe {{ {classes} }} "
                f"VALUES ?nom {{ {values} }} ?item wdt:P31 ?classe ; wdt:P225 ?nom . }}"
            )
            for b in await self._select(query, _BATCH_ATTEMPTS):
                qid = b["item"]["value"].rsplit("/", 1)[-1]
                if b["nom"]["value"] in found and qid not in found[b["nom"]["value"]]:
                    found[b["nom"]["value"]].append(qid)
        return found

    async def items_by_external_ids(self, pairs: Mapping[str, str]) -> list[str]:
        """Return the items holding any of the property to value pairs.

        Of any type: an id already set on an item reveals a duplicate
        that the name alone does not show.
        """
        if not pairs:
            return []
        values = " ".join(f'(wdt:{p} "{sparql_escape(v)}")' for p, v in pairs.items())
        query = (
            f"SELECT DISTINCT ?item WHERE {{ VALUES (?prop ?val) {{ {values} }} "
            f"?item ?prop ?val . }}"
        )
        bindings = await self._select(query, _BATCH_ATTEMPTS)
        return list(dict.fromkeys(b["item"]["value"].rsplit("/", 1)[-1] for b in bindings))

    async def _select(self, query: str, attempts: int) -> list[dict[str, Any]]:
        """Run a SPARQL SELECT, retrying on transport errors."""
        for attempt in range(attempts):
            try:
                resp = await self._client.get(
                    SPARQL_URL,
                    params={"query": query},
                    headers={"Accept": "application/sparql-results+json"},
                )
                break
            except httpx.TransportError:
                if attempt == attempts - 1:
                    raise
        resp.raise_for_status()
        bindings: list[dict[str, Any]] = resp.json().get("results", {}).get("bindings", [])
        return bindings

    async def qid(self, taxon: str) -> str | None:
        """Return the first item found by `qids`, or None."""
        found = await self.qids(taxon)
        return found[0] if found else None
