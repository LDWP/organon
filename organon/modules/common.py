"""Utilities shared by the module adapters.

REST pagination with truncation (`limite-listes`), debug link to the
source record, author formatting, synonym-loop guard. Most are pure or
thin wrappers over module callbacks; the ChecklistBank functions make
network calls, shared by all ChecklistBank adapters.
"""

from __future__ import annotations

import html as _html
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from organon.core.config import GenerateOptions
from organon.core.http import fetch_json
from organon.core.models import Struct, TaxonInfo
from organon.core.rendering.support import replace_et_al

__all__ = [
    "MAX_SYNONYM_HOPS",
    "as_limit",
    "checklistbank_accepted_name",
    "checklistbank_children_page",
    "checklistbank_synonyms",
    "collect_pages",
    "extract_aphia_original_description",
    "filter_ancestors_above_kingdom",
    "flatten_aphia_classification",
    "follow_synonym",
    "format_author",
    "format_author_year",
    "mediawiki_page_exists",
    "simple_debug_link",
    "sparql_escape",
]

logger = logging.getLogger(__name__)

# Guard against an endless loop when two taxa name each other as the
# accepted synonym; applied by every module that follows synonyms
# (see `hop` in each `collect()`).
MAX_SYNONYM_HOPS = 10


async def follow_synonym(
    struct: Struct,
    module_id: str,
    is_classification: bool,
    options: GenerateOptions,
    hop: int,
    resolve_accepted: Callable[[], Awaitable[str | None]],
    recurse: Callable[[int], Awaitable[Struct | None]],
) -> tuple[bool, Struct | None]:
    """Handle a synonym hit; return `(handled, result)`.

    When `handled` is false the caller keeps processing the synonym's
    own data (`follow_synonyms` off). Otherwise `result` is the value
    `collect()` must return. `resolve_accepted` yields the accepted
    name, or None; `recurse` re-runs the collection with a hop count.
    """
    if not is_classification:
        struct.links[module_id]["synonym"] = True
        return True, struct
    if not options.follow_synonyms:
        return False, None
    if hop >= MAX_SYNONYM_HOPS:
        return True, None
    accepted_name = await resolve_accepted()
    if accepted_name is None:
        return True, None
    struct.taxon = TaxonInfo(name=accepted_name)
    return True, await recurse(hop + 1)


async def checklistbank_accepted_name(usage: dict) -> str | None:
    """Return the accepted name of a ChecklistBank synonym usage."""
    accepted = usage.get("accepted")
    return accepted["name"]["scientificName"] if accepted is not None else None


async def collect_pages(
    fetch_page: Callable[[int], Awaitable[tuple[list, int, bool]]],
    start_offset: int = 0,
    limit: int | None = None,
) -> tuple[list, bool]:
    """Aggregate all pages of a paginated endpoint.

    `fetch_page(offset)` returns (kept items, raw page size, last
    page?). The raw size is distinct from the kept count when the caller
    filters records: advancing by the filtered count would overlap the
    next page and duplicate records. `start_offset` is 0 (GBIF) or 1
    (WoRMS); the next step comes from the raw size received.

    `limit` carries the `limite-listes` option: pagination stops once it
    is exceeded, to skip pages of a list truncated anyway. Return
    (items, truncated?).
    """
    items: list = []
    offset = start_offset
    while True:
        if limit is not None and len(items) > limit:
            return items[:limit], True
        page_items, raw_count, done = await fetch_page(offset)
        items.extend(page_items)
        offset += raw_count
        if done or not raw_count:
            break
    return items, False


def as_limit(options_value: int) -> int | None:
    """Convert `GenerateOptions.list_limit` to `collect_pages` `limit`.

    <=0 means no limit there, None here. `value or None` would keep -1.
    """
    return options_value if options_value > 0 else None


def format_author(author: str | None) -> str | None:
    """Decode HTML entities and rewrite "et al." in an author string.

    "et al." becomes `{{et al.}}`. Apply wherever a module writes an
    author into `Struct`. Return None for an empty input, to fit the
    optional Pydantic fields.
    """
    if not author:
        return None
    return replace_et_al(_html.unescape(author))


def format_author_year(authors: str | None, year: str | int | None) -> str | None:
    """Join author and year as "Author, Year".

    For sources exposing the year apart from the author citation (codes
    that omit it by convention, e.g. ICN). Apply no "et al."
    replacement: pass the result through `format_author`.
    """
    authors = authors or ""
    if year:
        authors = f"{authors}, {year}" if authors else str(year)
    return authors or None


_ORIGINAL_DESCRIPTION_FIELD_RE = re.compile(
    r'id="OriginalDescription"[^>]*>(?P<block>.*?)for="', re.DOTALL
)
_CORRECT_HTML_SPAN_RE = re.compile(r"correctHTML['\"]>(?P<texte>.*?)</span>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_aphia_original_description(html_page: str) -> str | None:
    """Extract the "Original description" of an Aphia detail page.

    Aphia is shared by WoRMS and IRMNG and has no REST field for it. The
    area is bounded by the next field's `for="`, as the HTML has no
    reliable end marker. Only the first citation is kept. Return None if
    the field is absent or empty.
    """
    field_match = _ORIGINAL_DESCRIPTION_FIELD_RE.search(html_page)
    if field_match is None:
        return None
    span_match = _CORRECT_HTML_SPAN_RE.search(field_match.group("block"))
    if span_match is None:
        return None
    text = _TAG_RE.sub("", span_match.group("texte"))
    # The work title is stored escaped (&lt;i&gt; or &lt;em&gt;): once
    # decoded, real tags to convert to wikitext italics rather than
    # leave as raw HTML (same as AlgaeBase's original publication).
    text = _html.unescape(text)
    text = re.sub(r"</?(?:i|em)>", "''", text).strip()
    return text or None


def flatten_aphia_classification(node: dict) -> list[dict]:
    """Flatten the nested Aphia classification tree to a list.

    Root first, leaf last. Shared by WoRMS and IRMNG.
    """
    chain = []
    cur: dict | None = node
    while cur is not None:
        chain.append(cur)
        cur = cur.get("child")
    return chain


def filter_ancestors_above_kingdom(
    chain: list[dict], kingdom_name: str, keep_kingdom: bool
) -> list[dict]:
    """Cut an ancestor chain at the kingdom.

    Any node at or above the kingdom is dropped, whatever rank the
    source declares: only the position of `kingdom_name` counts. If it
    is in no node, return the chain unchanged. `keep_kingdom` keeps the
    kingdom node itself (algae, protists; see KINGDOMS_KEPT_IN_CHAIN).
    """
    boundary = next(
        (i for i, node in enumerate(chain) if node.get("scientificname") == kingdom_name), None
    )
    if boundary is None:
        return chain
    rest = chain[boundary + 1 :]
    return [chain[boundary], *rest] if keep_kingdom else rest


def sparql_escape(value: str) -> str:
    """Escape a string for a double-quoted SPARQL literal.

    Backslash first, else the escaped quote would be re-escaped and a
    trailing backslash could merge with the closing quote (injection).
    Then newline and carriage return, which cannot appear raw.
    """
    return (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    )


async def mediawiki_page_exists(client: httpx.AsyncClient, api_url: str, title: str) -> bool:
    """Return True if a page exists, via the MediaWiki `action=query`.

    A missing page has `pageid: -1` and a `missing` key. Shared by the
    Commons, Wikispecies and Wiktionary adapters.
    """
    resp = await client.get(api_url, params={"action": "query", "titles": title, "format": "json"})
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    return any("missing" not in page for page in pages.values())


async def checklistbank_children_page(
    client: httpx.AsyncClient, api_base: str, dataset_id: str, taxon_id: str, offset: int = 0
) -> dict:
    """Return a page of ChecklistBank sub-taxa.

    Shared by all ChecklistBank adapters; failure-tolerant, see
    `checklistbank_synonyms`.
    """
    return await _checklistbank_get(
        client,
        f"{api_base}/dataset/{dataset_id}/tree/{taxon_id}/children",
        params={"offset": offset},
    )


async def checklistbank_synonyms(
    client: httpx.AsyncClient, api_base: str, dataset_id: str, taxon_id: str
) -> dict:
    """Return the ChecklistBank synonyms of a taxon.

    Shared by all ChecklistBank adapters except `coi_ioc`. Like
    `checklistbank_children_page`, it swallows network and HTTP errors:
    both run after a successful `search()` already wrote the
    classification, and an exception would discard it all.
    """
    return await _checklistbank_get(
        client, f"{api_base}/dataset/{dataset_id}/taxon/{taxon_id}/synonyms"
    )


async def _checklistbank_get(
    client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None = None
) -> dict:
    """GET a ChecklistBank URL, returning {} on a network error."""
    try:
        return await fetch_json(client, url, params=params, empty_value={})
    except httpx.HTTPError as exc:
        # Swallowed by design (see checklistbank_synonyms) but still
        # logged, or an outage would look like a taxon with no children
        # or synonyms.
        logger.warning("ChecklistBank injoignable sur %s : %s", url, exc)
        return {}


def simple_debug_link(struct: Struct, module_id: str, url_template: str, label: str) -> str | None:
    """Return a raw link to the taxon's page on the source site.

    Built from `struct.links[module_id]['id']`; `url_template` uses
    `{id}`, e.g. "https://www.gbif.org/species/{id}".
    """
    data = struct.links.get(module_id)
    if not data or "id" not in data:
        return None
    url = url_template.format(id=data["id"])
    return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{label}</a>"
