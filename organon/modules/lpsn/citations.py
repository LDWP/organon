"""Enrichment of the LPSN original publication.

LPSN exposes `publication_doi` as a structured field, so no scraping is
needed. The DOI is resolved by
`organon.modules.bibliography.resolve_doi_citation`, shared with WoRMS.
Out of scope: `ijsem_list_*` (Validation List) and `publication_pmid`.
Any failing step falls back on the raw `publication_text`: this is a
bonus, never a condition of success.
"""

from __future__ import annotations

from organon.modules.bibliography import LOOKUP_ERRORS
from organon.modules.lpsn.adapter import LpsnAdapter


def _wikify_italics(text: str) -> str:
    # Same convention as WoRMS and AlgaeBase for a work title possibly
    # italicized in the source text. `publication_text` is plain text on
    # the records checked, so this stays a harmless no-op.
    return text.replace("<i>", "''").replace("</i>", "''")


async def build_citation(adapter: LpsnAdapter, record: dict) -> str | None:
    """Return the citation of the record, via its DOI if resolvable."""
    text = record.get("publication_text")
    doi = record.get("publication_doi")
    if doi:
        try:
            enriched = await adapter.resolve_doi_citation(doi)
            if enriched:
                return enriched
        except LOOKUP_ERRORS:
            pass
    return _wikify_italics(text) if text else None
