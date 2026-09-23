"""Shared resolution of a DOI into a structured wikitext citation.

Wikidata (P356) first, giving `{{Bibliographie|Qxxx}}` when the work is
already listed; else Crossref, to build `{{Article}}` or `{{Ouvrage}}`
by hand from `message["type"]`. Shared by every module that can find a
DOI in its data (WoRMS, LPSN); only how the DOI is found differs, and
stays in the module (`citations.py`).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import httpx

from organon.core.http import USER_AGENT
from organon.modules.common import sparql_escape

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
CROSSREF_URL = "https://api.crossref.org/works"

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)

# What callers (`*/citations.py::build_citation`) catch to fall back on
# their raw text: any network or JSON step may fail without it being an
# error of the calling module.
LOOKUP_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError)

# Crossref types identifying a book; an article stays an {{Article}}
# rather than a mislabeled {{Ouvrage}}.
_CROSSREF_BOOK_TYPES = {"book", "monograph", "edited-book", "reference-book"}


async def _wikidata_qid_for_doi(client: httpx.AsyncClient, doi: str) -> str | None:
    """Return the QID of the Wikidata item holding this DOI (P356).

    Case-insensitive through `UCASE`: Wikidata uppercases P356 by
    convention, not for every entry.
    """
    query = (
        "SELECT ?item WHERE "
        f'{{ ?item wdt:P356 ?doi . FILTER(UCASE(STR(?doi)) = UCASE("{sparql_escape(doi)}")) }}'
    )
    resp = await client.get(
        WIKIDATA_SPARQL_URL,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    if not bindings:
        return None
    return bindings[0]["item"]["value"].rsplit("/", 1)[-1]


async def _crossref_work(client: httpx.AsyncClient, doi: str) -> dict | None:
    """Return the Crossref metadata of a DOI, or None if unknown."""
    resp = await client.get(f"{CROSSREF_URL}/{doi}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("message")


def build_template(name: str, fields: list[tuple[str, str]], required: set[str]) -> str | None:
    """Build `{{name | ...}}` from the non-empty fields.

    Return None if a parameter of `required` is missing (see
    Modèle:Article and Modèle:Ouvrage on frwiki): better to skip the
    enrichment than show a broken citation. Public: reused by
    `wrms/citations.py` for BHL metadata.
    """
    presents = {key for key, value in fields if value}
    if not required <= presents:
        return None
    params = " | ".join(f"{key}={value}" for key, value in fields if value)
    return f"{{{{{name} | {params}}}}}"


def _crossref_authors(message: dict) -> list[str]:
    """Return the "Given Family" author names of a Crossref work."""
    return [
        " ".join(part for part in (author.get("given"), author.get("family")) if part)
        for author in message.get("author", [])
        if author.get("family")
    ]


def _crossref_year(message: dict) -> str:
    """Return the publication year of a Crossref work, or ""."""
    for key in ("published-print", "published", "issued"):
        parts = message.get(key, {}).get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return ""


def _build_article_from_crossref(doi: str, message: dict) -> str | None:
    """Build an `{{Article}}` from Crossref metadata."""
    fields = [(f"auteur{i}", a) for i, a in enumerate(_crossref_authors(message), start=1)]
    fields += [
        ("titre", (message.get("title") or [""])[0]),
        ("périodique", (message.get("container-title") or [""])[0]),
        ("volume", message.get("volume", "")),
        ("numéro", message.get("issue", "")),
        ("date", _crossref_year(message)),
        ("pages", message.get("page", "")),
        ("doi", doi),
    ]
    return build_template("Article", fields, {"titre", "périodique", "date"})


def _build_book_from_crossref(doi: str, message: dict) -> str | None:
    """Build an `{{Ouvrage}}` from Crossref metadata."""
    fields = [(f"auteur{i}", a) for i, a in enumerate(_crossref_authors(message), start=1)]
    fields += [
        ("titre", (message.get("title") or [""])[0]),
        ("éditeur", message.get("publisher", "")),
        ("année", _crossref_year(message)),
    ]
    return build_template("Ouvrage", fields, {"titre"})


async def resolve_doi_citation(client: httpx.AsyncClient, doi: str) -> str | None:
    """Resolve a DOI into a wikitext citation.

    Wikidata first, giving `{{Bibliographie|Qxxx}}`, else Crossref for
    `{{Article}}` or `{{Ouvrage}}` by `message["type"]`. Return None if
    neither works; the caller picks the fallback.
    """
    qid = await _wikidata_qid_for_doi(client, doi)
    if qid:
        return f"{{{{Bibliographie|{qid}}}}}"
    message = await _crossref_work(client, doi)
    if not message:
        return None
    if message.get("type") in _CROSSREF_BOOK_TYPES:
        return _build_book_from_crossref(doi, message)
    return _build_article_from_crossref(doi, message)


def extract_doi(text: str) -> str | None:
    """Return the DOI found in a text, without trailing punctuation."""
    match = DOI_RE.search(text)
    if match is None:
        return None
    # The surrounding prose may leave a trailing punctuation mark that
    # is not part of the DOI.
    return match.group(0).rstrip(".,;)]")


async def citation_or_text(
    resolve: Callable[[str], Awaitable[str | None]], text: str | None
) -> str | None:
    """Return the structured citation of the DOI in `text`, else `text`.

    `resolve` is an adapter's `resolve_doi_citation`. A bonus, never a
    condition of success: any lookup failure keeps the source text.
    """
    if not text:
        return text
    doi = extract_doi(text)
    if doi:
        try:
            enriched = await resolve(doi)
        except LOOKUP_ERRORS:
            return text
        if enriched:
            return enriched
    return text
