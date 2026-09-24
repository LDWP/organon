"""Enrichment of the WoRMS original publication.

When a DOI is found in the scraped text, delegate to
`organon.modules.bibliography.resolve_doi_citation` (shared with LPSN).
Without a DOI, a biodiversitylibrary.org link triggers the same
enrichment through the BHL API, the only way to get a structured title,
authors and publisher: the surrounding WoRMS text is free prose, too
unreliable to parse. A BHL record sometimes holds a Wikidata id
(`Title.Identifiers`): if the item is an edition (P31=Q3331189, not the
generic work), `{{Bibliographie}}` takes precedence over a hand-built
`{{Ouvrage}}`.

Any failing step falls back on the raw text: this is a bonus, never a
condition of success of the WoRMS module.
"""

from __future__ import annotations

import re

from organon.modules.bibliography import LOOKUP_ERRORS, build_template, extract_doi
from organon.modules.wrms.adapter import WrmsAdapter

_BHL_URL_RE = re.compile(r"https?://(?:www\.)?biodiversitylibrary\.org/page/(\d+)[^\s\"'<>]*")
_QID_RE = re.compile(r"^Q[1-9]\d*$")

# BHL Title/Genre values identifying a book (API v3 "Data Elements"): an
# article or serial issue stays raw text rather than a mislabeled
# {{Ouvrage}}.
_BHL_BOOK_GENRES = {"Monograph/Item", "Collection"}


def _bhl_wikidata_qid(title: dict) -> str | None:
    """Return the Wikidata QID listed in a BHL title, or None."""
    for identifier in title.get("Identifiers", []):
        if identifier.get("IdentifierName") == "Wikidata":
            value = identifier.get("IdentifierValue", "")
            if _QID_RE.match(value):
                return value
    return None


async def _via_bhl(adapter: WrmsAdapter, page_url: str, page_id: str) -> str | None:
    """Build an `{{Ouvrage}}` or `{{Bibliographie}}` from BHL."""
    page = await adapter.bhl_page_metadata(page_id)
    if not page:
        return None
    item = await adapter.bhl_item_metadata(page["ItemID"])
    if not item:
        return None
    title = await adapter.bhl_title_metadata(item["TitleID"])
    if not title or title.get("Genre") not in _BHL_BOOK_GENRES:
        return None
    qid = _bhl_wikidata_qid(title)
    if qid and await adapter.wikidata_is_edition(qid):
        return f"{{{{Bibliographie|{qid}}}}}"
    authors = enumerate((a for a in title.get("Authors", []) if a.get("Name")), start=1)
    fields = [(f"auteur{i}", a["Name"]) for i, a in authors]
    fields += [
        ("titre", title.get("FullTitle") or title.get("ShortTitle", "")),
        ("lieu", title.get("PublisherPlace", "")),
        ("éditeur", title.get("PublisherName", "")),
        ("année", str(item.get("Year") or title.get("PublicationDate", ""))),
        ("lire en ligne", page_url),
    ]
    return build_template("Ouvrage", fields, {"titre"})


async def build_citation(adapter: WrmsAdapter, raw_text: str | None) -> str | None:
    """Return a structured citation for the raw text, else the text."""
    if not raw_text:
        return raw_text
    try:
        doi = extract_doi(raw_text)
        if doi:
            enriched = await adapter.resolve_doi_citation(doi)
            if enriched:
                return enriched
        bhl_match = _BHL_URL_RE.search(raw_text)
        if bhl_match:
            enriched = await _via_bhl(adapter, bhl_match.group(0), bhl_match.group(1))
            if enriched:
                return enriched
    except LOOKUP_ERRORS:
        pass
    return raw_text
