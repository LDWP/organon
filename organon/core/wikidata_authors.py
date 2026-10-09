"""Resolve botanical author abbreviations through Wikidata (P428).

Fallback for abbreviations missing from `auteurs_botanistes.yaml`. The
cache is per-process (the `Procfile` starts a single worker); network
failures are never cached: a transient outage hides no author.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Iterable

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin

__all__ = [
    "WIKIDATA_API",
    "clear_cache",
    "lookup_author_qids",
    "normalize_abbreviation",
]

logger = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_TTL_SECONDS = 24 * 3600
_TIMEOUT_SECONDS = 5.0

# abbreviation -> (expiry, QID or None when unknown/ambiguous)
_cache: dict[str, tuple[float, str | None]] = {}


def normalize_abbreviation(abbreviation: str) -> str:
    """Return the P428 form: no space after a dot."""
    return re.sub(r"\.\s+", ".", abbreviation.strip())


def clear_cache() -> None:
    """Drop every cached lookup."""
    _cache.clear()


async def lookup_author_qids(abbreviations: Iterable[str]) -> dict[str, str]:
    """Map each normalized abbreviation to the QID carrying it as P428.

    Abbreviations unknown to Wikidata, shared by several entities, or
    hit by a network error are omitted.
    """
    keys = dict.fromkeys(normalize_abbreviation(a) for a in abbreviations)
    now = time.monotonic()
    missing = [k for k in keys if k not in _cache or _cache[k][0] <= now]
    if missing:
        async with _AuthorsClient() as client:
            await asyncio.gather(*(client.fetch(k) for k in missing))
    return {k: qid for k in keys if (qid := _cache.get(k, (0.0, None))[1]) is not None}


class _AuthorsClient(OwnedClientMixin):
    def __init__(self) -> None:
        super().__init__(timeout=_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})

    async def fetch(self, abbreviation: str) -> None:
        try:
            resp = await self._client.get(
                WIKIDATA_API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": f"haswbstatement:P428={abbreviation}",
                    "srlimit": "2",
                    "format": "json",
                    "formatversion": "2",
                },
            )
            resp.raise_for_status()
            hits = resp.json()["query"]["search"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Wikidata indisponible pour l'auteur « %s » : %s", abbreviation, exc)
            return
        qid = hits[0]["title"] if len(hits) == 1 else None
        _cache[abbreviation] = (time.monotonic() + _TTL_SECONDS, qid)
