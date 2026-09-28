"""GET /api/v1/search: fuzzy search by scientific or vernacular name.

Uses `GbifAdapter.search_any` (`species/search`), which matches
"Gadus morhua" as well as "morue franche" and returns one result
per kingdom for a homonym (e.g. "Morus"). Each `SearchMatch`
carries `gbif_key` and `parent_key`, so the frontend can confirm a
real parentage between suggestions instead of guessing from names.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request

from organon.api.deps import require_username
from organon.api.rate_limit import SEARCH_RATE_LIMIT, limiter
from organon.api.schemas import SearchMatch, SearchResponse
from organon.core.domains import KINGDOM_MAP
from organon.core.rendering.grammar import wp_rank_name
from organon.modules.gbif.adapter import GbifAdapter
from organon.modules.gbif.ranks import gbif_to_wp_rank
from organon.modules.wikidata.adapter import WikidataEntityAdapter

router = APIRouter()

MAX_MATCHES = 8
MAX_VERNACULAR_PER_MATCH = 5

_QID_RE = re.compile(r"^Q[1-9]\d*$", re.IGNORECASE)

DedupKey = int | tuple[str, str, str]


def _preferred_vernaculars(raw: list[dict]) -> list[str]:
    """Return up to five vernacular names, French first."""
    french = [v["vernacularName"] for v in raw if v.get("language") == "fra"]
    others = [v["vernacularName"] for v in raw if v.get("language") != "fra"]
    seen: dict[str, None] = {}
    for name in french + others:
        seen.setdefault(name, None)
    return list(seen)[:MAX_VERNACULAR_PER_MATCH]


def _relevance(match: SearchMatch, query: str) -> int:
    """Rank an exact scientific, then vernacular, match first.

    `species/search` mixes homonyms and variants without always
    putting the requested name first.
    """
    query_lower = query.lower()
    if match.scientific_name.lower() == query_lower:
        return 0
    if any(v.lower() == query_lower for v in match.vernacular_names):
        return 1
    return 2


def _clean_name(entry: dict) -> str | None:
    """Return the scientific name without its authorship, or None.

    Prefers `scientificName` over `canonicalName`, which drops the
    "subsp."/"var." marker of infraspecific plants. `authorship` is
    always a literal suffix of `scientificName`.
    """
    name = entry.get("scientificName") or entry.get("canonicalName")
    if not name:
        return None
    # `.strip()`: GBIF may return `authorship` with a trailing space
    # absent from the same suffix of `scientificName`, which would make
    # `endswith` fail and break the exact match of `_relevance`.
    author = (entry.get("authorship") or "").strip()
    if author and name.endswith(author):
        name = name[: -len(author)].rstrip()
    return name or None


def _doubtful_rank(status: str) -> int:
    """Break `_relevance` ties: DOUBTFUL sorts after the others.

    Python's sort is stable, so an unfavorable raw order would
    otherwise decide the default `gbif_key`.
    """
    return 1 if status == "DOUBTFUL" else 0


def _rank_label(rank_raw: str) -> str:
    """Translate a GBIF rank to the French label used app-wide."""
    rank_id = gbif_to_wp_rank(rank_raw)
    if rank_id is None:
        return rank_raw.lower()
    return wp_rank_name(rank_id, False, False, False) or rank_raw.lower()


@router.get("/search", response_model=SearchResponse)
@limiter.limit(SEARCH_RATE_LIMIT)
async def search(
    request: Request, q: str, username: str = Depends(require_username)
) -> SearchResponse:
    """Return suggestions for a name, or the item for a Wikidata QID."""
    query = q.strip()
    if not query:
        return SearchResponse(query=q, matches=[])

    if _QID_RE.match(query):
        return await _search_by_qid(query.upper())

    async with GbifAdapter() as adapter:
        raw_results = await adapter.search_any(query, limit=30)

    # Deduplicated by GBIF `key`, not by (name, kingdom): distinct taxa
    # can share both (e.g. "Acanthocephala", a phylum and an insect
    # genus, both Animalia).
    seen: dict[DedupKey, tuple[SearchMatch, int]] = {}
    for entry in raw_results:
        found_name = _clean_name(entry)
        if not found_name:
            continue
        kingdom_raw = entry.get("kingdom", "")
        dedup_key: DedupKey = entry.get("key") or (
            found_name,
            kingdom_raw,
            entry.get("authorship", ""),
        )
        if dedup_key in seen:
            continue
        match = SearchMatch(
            scientific_name=found_name,
            author=entry.get("authorship", "").strip(),
            extinct=bool(entry.get("extinct", False)),
            kingdom=KINGDOM_MAP.get(kingdom_raw, kingdom_raw.lower()),
            rank=_rank_label(entry.get("rank", "")),
            vernacular_names=_preferred_vernaculars(entry.get("vernacularNames", [])),
            gbif_key=entry.get("key"),
            parent_key=entry.get("parentKey"),
        )
        seen[dedup_key] = (match, _doubtful_rank(entry.get("taxonomicStatus", "")))

    # Sort by relevance before cutting to MAX_MATCHES, or the exact
    # match could be lost if GBIF returns it late.
    ordered = sorted(seen.values(), key=lambda pair: (_relevance(pair[0], query), pair[1]))
    matches = [match for match, _ in ordered][:MAX_MATCHES]
    return SearchResponse(query=q, matches=matches)


async def _search_by_qid(qid: str) -> SearchResponse:
    """Resolve a Wikidata QID to a single `SearchMatch`.

    It carries the external ids the item already knows. A QID names a
    precise item, so no relevance or deduplication applies.
    """
    async with WikidataEntityAdapter() as adapter:
        entity = await adapter.get_entity(qid)
        if entity is None:
            return SearchResponse(query=qid, matches=[])

        name = adapter.taxon_name(entity)
        if not name:
            return SearchResponse(query=qid, matches=[])

        match = SearchMatch(
            scientific_name=name,
            source="Wikidata",
            qid=qid,
            external_ids=adapter.external_ids(entity),
        )
        return SearchResponse(query=qid, matches=[match])
