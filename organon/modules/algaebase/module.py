"""AlgaeBase module: classification, sub-taxa, etymology, publication.

Makes no HTTP call itself; see adapter.py.

Three searches depending on the number of words of the taxon: species
(>= 2 words), then genus, falling back on "higher rank" if the genus
search fails.

API quirk: some detail endpoints sometimes return the JSON string
`"Nothing Found"` rather than an empty object when an id has no data
(e.g. `/genus/{id}/detail` with no detail page), hence the
`isinstance(..., dict)` checks before any `.get()`.
"""

from __future__ import annotations

import asyncio
import re
from typing import cast

from organon.core.config import GenerateOptions
from organon.core.models import Etymology, LinkEntry, RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.algaebase.adapter import AlgaeBaseAdapter
from organon.modules.algaebase.ranks import algaebase_charter_kingdom, algaebase_to_wp_rank
from organon.modules.bibliography import citation_or_text
from organon.modules.common import format_author, format_author_year, simple_debug_link

PAGE_SIZE = 50


def _format_author_year(found: dict) -> str:
    """Return the author and year of a record, or ""."""
    return (
        format_author_year(
            found.get("dwc:scientificNameAuthorship"), found.get("dwc:namePublishedInYear")
        )
        or ""
    )


def _base_blob(found: dict, taxon_name: str, id_field: str) -> LinkEntry:
    """Build the `links` entry of a found record."""
    blob: LinkEntry = {
        "rank": algaebase_to_wp_rank(found.get("dwc:taxonRank", "")),
        "name": taxon_name,
        "id": found.get(id_field),
    }
    author = _format_author_year(found)
    if author:
        blob["author"] = format_author(author)
    if found.get("isFossil") == "Y" or found.get("dwc:isFossil") == "Y":
        blob["extinct"] = True
    return blob


def _blob_to_taxon(blob: LinkEntry) -> TaxonInfo:
    """Build a `TaxonInfo` from a `links` entry."""
    return TaxonInfo(
        name=blob["name"],
        rank=blob.get("rank"),
        author=blob.get("author"),
        extinct=blob.get("extinct"),
    )


def _to_rankname(entry: LinkEntry) -> RankName:
    """Build a `RankName` from a `links` entry."""
    return RankName(
        name=entry["name"],
        rank=entry.get("rank"),
        author=entry.get("author"),
        extinct=entry.get("extinct"),
    )


def _extract_classification(items: list[dict]) -> tuple[list[LinkEntry], str, str]:
    """Return (entries, phylum, kingdom) from a classification list.

    It does not identify the "genus" entry itself: the caller (genus
    branch of `collect()`) finds it in a separate loop; see
    `_collect_genus`.
    """
    out: list[LinkEntry] = []
    phylum = ""
    kingdom = ""
    for cl in items:
        raw_rank = cl.get("dwc:taxonRank") or ""
        if raw_rank.lower() == "empire":
            continue
        if raw_rank.lower() == "kingdom":
            kingdom = cl.get("dwc:scientificName") or ""
        if raw_rank.lower() == "phylum":
            phylum = cl.get("dwc:scientificName") or ""
        author = _format_author_year(cl).replace("& al.", "et al.")
        out.append(
            {
                "rank": algaebase_to_wp_rank(raw_rank),
                "id": cl.get("dwc:taxonID"),
                "name": (cl.get("dwc:scientificName") or "").strip(),
                "author": format_author(author) if author else None,
            }
        )
    return out, phylum, kingdom


def _apply_etymology(struct: Struct, found: dict) -> None:
    """Set the etymology from the record, if any."""
    origin = found.get("nameOrigin")
    if origin:
        text = re.sub(r"[.]\s*$", "", origin)
        struct.etymology = Etymology(text=f"''{text}''", source="AlgaeBASE")


async def _apply_bibliographic_citation(
    adapter: AlgaeBaseAdapter, struct: Struct, found: dict
) -> None:
    """Set the original publication from the record citation."""
    citation = found.get("dcterms:bibliographicCitation")
    if not citation:
        return
    text = await citation_or_text(
        adapter.resolve_doi_citation, citation.replace("<i>", "''").replace("</i>", "''")
    )
    pdfs = found.get("pdfs") or []
    if text and pdfs and pdfs[0].get("pdf_url"):
        text += f" ([{pdfs[0]['pdf_url']} PDF])"
    struct.original_publication = text


async def _apply_detail_page(adapter: AlgaeBaseAdapter, struct: Struct, details: dict) -> None:
    """Set description and original publication from the page."""
    desc = details.get("description")
    if desc:
        bucket = struct.description.setdefault("AlgaeBASE", [])
        bucket.append(f"''{desc}''")
    publication = details.get("originalPublicationRef")
    if publication:
        struct.original_publication = await citation_or_text(
            adapter.resolve_doi_citation, publication.replace("<i>", "''").replace("</i>", "''")
        )


async def _find_species(adapter: AlgaeBaseAdapter, key: str, taxon: str) -> dict | None:
    """Return the species record whose name equals `taxon`, or None."""
    offset = 0
    while True:
        res = await adapter.search_species_page(key, taxon, offset)
        if res is None:
            return None
        results = res.get("result")
        pagination = res.get("_pagination") or {}
        total = pagination.get("_total_number_of_results")
        if results is None or total is None:
            return None
        for r in results:
            name = r.get("dwc:scientificName") or ""
            authorship = r.get("dwc:scientificNameAuthorship") or ""
            if authorship:
                name = name.replace(f" {authorship}", "")
            if name == taxon:
                return r
        offset += PAGE_SIZE
        if offset >= total:
            return None


async def _collect_species(
    adapter: AlgaeBaseAdapter,
    key: str,
    struct: Struct,
    is_classification: bool,
    options: GenerateOptions,
) -> Struct | None:
    """Collect a species."""
    taxon = struct.taxon.name
    found = await _find_species(adapter, key, taxon)
    if found is None:
        return None

    accepted_id = found.get("dwc:acceptedNameUsageID")
    if accepted_id is not None:
        detail_resp = await adapter.species_detail(key, accepted_id)
        if detail_resp and detail_resp.get("details"):
            found = detail_resp["details"]

    blob: LinkEntry = _base_blob(found, taxon, id_field="dwc:acceptedNameUsageID")
    struct.links["algaebase"] = blob

    if not is_classification:
        return struct

    genus_id = found.get("genusID")

    struct.taxon = _blob_to_taxon(blob)
    struct.classification = "AlgaeBASE"
    struct.classification_taxobox = "AlgaeBASE"

    await _apply_bibliographic_citation(adapter, struct, found)
    _apply_etymology(struct, found)

    tbl: list[str] = []
    if found.get("dwc:isMarine"):
        tbl.append("Cette espèce est marine")
    if found.get("dwc:isFreshwater"):
        tbl.append("Cette espèce vit en eau douce")
    if found.get("dwc:isTerrestrial"):
        tbl.append("Cette espèce est terrestre")
    if tbl:
        struct.description["AlgaeBASE"] = tbl

    if genus_id is None:
        return struct

    # `genus_id` (found["genusID"]) and blob["id"]
    # (found["dwc:acceptedNameUsageID"]) are independent keys of the
    # same `found`, already resolved: the two detail calls can run in
    # parallel. blob["id"] may be missing (synonym resolution without
    # accepted id): skip the call rather than hit /taxonomy/None/detail,
    # as for species_detail() above.
    page_detail_call = (
        adapter.taxonomy_page_detail(key, cast(int, blob["id"]))
        if blob["id"] is not None
        else asyncio.sleep(0, result=None)
    )
    genus_detail, page_detail = await asyncio.gather(
        adapter.genus_detail(key, genus_id), page_detail_call
    )
    if genus_detail is None or "classification" not in genus_detail:
        return None
    rank_tbl, phylum, kingdom = _extract_classification(genus_detail["classification"])
    struct.ranks = [_to_rankname(r) for r in reversed(rank_tbl)]

    struct.kingdom = algaebase_charter_kingdom(phylum, kingdom)
    if struct.kingdom != "algue":
        struct.hide_kingdom = True

    if isinstance(page_detail, dict):
        await _apply_detail_page(adapter, struct, page_detail.get("details") or {})

    return struct


async def _collect_genus(
    adapter: AlgaeBaseAdapter,
    key: str,
    struct: Struct,
    is_classification: bool,
    options: GenerateOptions,
) -> Struct | None:
    """Collect a genus."""
    taxon = struct.taxon.name
    res = await adapter.search_genus(key, taxon)
    if res is None:
        return None
    results = res.get("result")
    pagination = res.get("_pagination") or {}
    if results is None or "_total_number_of_results" not in pagination:
        return None

    found = None
    for r in results:
        if r.get("dwc:taxonRank") != "genus":
            continue
        name = r.get("dwc:scientificName")
        if not name:
            continue
        if name.split(" ")[0] != taxon:
            continue
        found = r
        break
    if found is None:
        return None

    blob: LinkEntry = _base_blob(found, taxon, id_field="dwc:acceptedNameUsageID")
    struct.links["algaebase"] = blob

    if not is_classification:
        return struct

    taxon_id = found.get("dwc:acceptedNameUsageID")

    struct.taxon = _blob_to_taxon(blob)
    struct.classification = "AlgaeBASE"
    struct.classification_taxobox = "AlgaeBASE"

    _apply_etymology(struct, found)
    await _apply_bibliographic_citation(adapter, struct, found)

    detail = await adapter.genus_detail(key, taxon_id)
    if detail is None or "classification" not in detail:
        return None
    rank_tbl, phylum, kingdom = _extract_classification(detail["classification"])

    c_id = None
    filtered: list[LinkEntry] = []
    for cont in reversed(rank_tbl):
        if cont["rank"] == "genre":
            c_id = cast(int, cont["id"])
            continue
        filtered.append(cont)
    struct.ranks = [_to_rankname(r) for r in filtered]

    sub_detail = await adapter.taxonomy_detail(key, c_id) if c_id is not None else None
    lower = sub_detail.get("lowerTaxa") if isinstance(sub_detail, dict) else None
    if lower:
        sub_tbl, _, _ = _extract_classification(lower)
        if sub_tbl:
            struct.subtaxa = SubTaxonList(
                items=[_to_rankname(r) for r in sub_tbl], source="AlgaeBASE"
            )

    struct.kingdom = algaebase_charter_kingdom(phylum, kingdom)
    if struct.kingdom != "algue":
        struct.hide_kingdom = True

    page_detail = await adapter.taxonomy_page_detail(key, taxon_id)
    if isinstance(page_detail, dict):
        await _apply_detail_page(adapter, struct, page_detail.get("details") or {})

    return struct


async def _collect_superior(
    adapter: AlgaeBaseAdapter,
    key: str,
    struct: Struct,
    is_classification: bool,
    options: GenerateOptions,
) -> Struct | None:
    """Collect a higher taxon."""
    taxon = struct.taxon.name
    res = await adapter.search_taxonomy(key, taxon)
    if res is None:
        return None
    results = res.get("result")
    pagination = res.get("_pagination") or {}
    if results is None or "_total_number_of_results" not in pagination:
        return None

    found = None
    for r in results:
        if r.get("dwc:scientificName") == taxon:
            found = r
            break
    if found is None:
        return None

    blob: LinkEntry = _base_blob(found, taxon, id_field="dwc:taxonID")
    struct.links["algaebase"] = blob

    if not is_classification:
        return struct

    taxon_id = found.get("dwc:taxonID")

    struct.taxon = _blob_to_taxon(blob)
    struct.classification = "AlgaeBASE"
    struct.classification_taxobox = "AlgaeBASE"

    _apply_etymology(struct, found)
    await _apply_bibliographic_citation(adapter, struct, found)

    detail = await adapter.taxonomy_detail(key, taxon_id)
    if detail is None or "higherTaxa" not in detail:
        return None
    higher_tbl, phylum, kingdom = _extract_classification(detail["higherTaxa"])
    struct.ranks = [
        _to_rankname(r) for r in reversed(higher_tbl) if r["rank"] != struct.taxon.rank
    ]

    lower = detail.get("lowerTaxa")
    if lower:
        sub_tbl, _, _ = _extract_classification(lower)
        if sub_tbl:
            struct.subtaxa = SubTaxonList(
                items=[_to_rankname(r) for r in sub_tbl], source="AlgaeBASE"
            )

    struct.kingdom = algaebase_charter_kingdom(phylum, kingdom)
    if struct.kingdom != "algue":
        struct.hide_kingdom = True

    page_detail = await adapter.taxonomy_page_detail(key, taxon_id)
    if isinstance(page_detail, dict):
        await _apply_detail_page(adapter, struct, page_detail.get("details") or {})

    return struct


_SPECIES_RANKS = {"espèce", "sous-espèce", "forme", "variété", "pathovar", "cultivar"}
_GENUS_RANKS = {"genre", "sous-genre"}


class AlgaeBaseModule(TaxonomyModule):
    """AlgaeBase module."""

    meta = ModuleMeta(
        id="algaebase",
        can_classify=True,
        can_render_external_link=True,
        domains=["champignon", "algue", "végétal", "archaea", "bactérie", "protiste"],
        priority=990,
    )

    def __init__(self, adapter: AlgaeBaseAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or AlgaeBaseAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from AlgaeBase."""
        adapter = self._adapter
        key = await adapter.fetch_key()
        if key is None:
            return None

        taxon = struct.taxon.name
        if len(taxon.split(" ")) >= 2:
            return await _collect_species(adapter, key, struct, is_classification, options)

        result = await _collect_genus(adapter, key, struct, is_classification, options)
        if result is not None:
            return result
        return await _collect_superior(adapter, key, struct, is_classification, options)

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{AlgaeBASE}} template."""
        data = struct.links.get("algaebase")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        rank = data.get("rank") or struct.taxon.rank
        name = wp_apply_italics(data["name"], rank, struct.kingdom)
        if author := data.get("author"):
            name += " " + author
        extinct = " éteint=oui |" if data.get("extinct") else ""
        if rank in _SPECIES_RANKS:
            type_, extinct_param = " espèce", ""
        elif rank in _GENUS_RANKS:
            type_, extinct_param = " genre", ""
        else:
            type_, extinct_param = "", f" {rank} |"
        return (
            f"{{{{AlgaeBASE{type_} | {data['id']} | {name} |{extinct_param}{extinct} consulté "
            f"le={cdate}}}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the AlgaeBase page."""
        return simple_debug_link(
            struct,
            "algaebase",
            "https://www.algaebase.org/search/species/detail/?species_id={id}",
            "AlgaeBase",
        )


register_module(AlgaeBaseModule)
