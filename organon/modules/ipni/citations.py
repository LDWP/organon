"""Enrichment of the IPNI original publication.

IPNI has no structured DOI field, but a DOI sometimes appears as free
text in `remarks`, mixed with other notes; absent for names older than
DOIs. It is resolved by
`organon.modules.bibliography.resolve_doi_citation`, shared with WoRMS
and LPSN. Without a usable DOI, fall back on `reference`, the free-text
citation always present on an IPNI name record.

Deliberately not resolved: `linkedPublication.bhlTitleLink` is an
OpenURL, not a direct BHL id usable by `WrmsAdapter.bhl_title_metadata`.
"""

from __future__ import annotations

from organon.modules.bibliography import LOOKUP_ERRORS, extract_doi
from organon.modules.ipni.adapter import IpniAdapter


async def build_citation(adapter: IpniAdapter, match: dict) -> str | None:
    """Return the citation of a name record, via its DOI if any."""
    remarks = match.get("remarks") or ""
    doi = extract_doi(remarks)
    if doi:
        try:
            enriched = await adapter.resolve_doi_citation(doi)
            if enriched:
                return enriched
        except LOOKUP_ERRORS:
            pass
    return match.get("reference")
