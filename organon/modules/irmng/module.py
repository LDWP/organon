"""IRMNG module: classification, synonyms, sub-taxa, vernacular names.

Through the REST API (see adapter.py). Same architecture as
`organon/modules/wrms/module.py`: IRMNG runs on the same Aphia/VLIZ
platform and answers with a nearly identical shape (`kingdom`,
`authority`, `isExtinct`, `originalNameUsageID` for the basionym,
`valid_IRMNG_ID` for synonym following).

IRMNG is a fallback generalist (all kingdoms, often stopping at the
genus): `ModuleMeta.priority` stays at the default 0, below GBIF, ITIS,
WoRMS and AlgaeBase.

The original publication has no structured REST field: it is scraped
from the HTML detail page, the one exception to "REST only".

The "non valide" suffix of a synonym (`render_bioref`) does not name the
accepted target: IRMNG does not provide it at render time.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.langues import groupe_par_langue
from organon.core.models import (
    Basionym,
    LinkEntry,
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.bibliography import citation_or_text
from organon.modules.common import (
    as_limit,
    collect_pages,
    filter_ancestors_above_kingdom,
    flatten_aphia_classification,
    follow_synonym,
    format_author,
    simple_debug_link,
)
from organon.modules.irmng.adapter import IrmngAdapter
from organon.modules.irmng.ranks import (
    KINGDOMS_KEPT_IN_CHAIN,
    irmng_charter_kingdom,
    irmng_to_wp_rank,
)

PAGE_SIZE = 50


class IrmngModule(TaxonomyModule):
    """IRMNG module."""

    meta = ModuleMeta(id="irmng", can_classify=True, can_render_external_link=True, domains="all")

    def __init__(self, adapter: IrmngAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or IrmngAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from IRMNG."""
        results = await self._adapter.records_by_name(struct.taxon.name)
        if not results:
            return None
        cur = next((r for r in results if r.get("status") == "accepted"), None)
        if cur is None:
            if not options.follow_synonyms:
                return None
            cur = results[0]
        return await self._process(struct, cur, is_classification, options, hop=0)

    async def _process(
        self,
        struct: Struct,
        cur: dict,
        is_classification: bool,
        options: GenerateOptions,
        hop: int,
    ) -> Struct | None:
        """Process the chosen record, following a synonym if needed."""
        adapter = self._adapter
        irmng_id = cur["IRMNG_ID"]

        irmng_link: LinkEntry = {
            "id": irmng_id,
            "name": cur["scientificname"],
            "rank": irmng_to_wp_rank(cur["rank"]),
        }
        if cur.get("authority"):
            irmng_link["author"] = format_author(cur["authority"])
        if cur.get("isExtinct"):
            irmng_link["extinct"] = True
        struct.links["irmng"] = irmng_link

        is_synonym = cur.get("valid_IRMNG_ID") is not None and cur["valid_IRMNG_ID"] != irmng_id
        if is_synonym:
            accepted: dict | None = None

            async def resolve_accepted() -> str | None:
                nonlocal accepted
                accepted = await adapter.record_by_id(cur["valid_IRMNG_ID"])
                return accepted["scientificname"] if accepted is not None else None

            async def recurse_accepted(next_hop: int) -> Struct | None:
                assert accepted is not None  # follow_synonym recurses only once resolved
                return await self._process(
                    struct, accepted, is_classification, options, hop=next_hop
                )

            handled, result = await follow_synonym(
                struct,
                "irmng",
                is_classification,
                options,
                hop,
                resolve_accepted,
                recurse_accepted,
            )
            if handled:
                return result
            # follow_synonyms is off: keep going with the synonym as is

        if not is_classification:
            return struct

        if not cur.get("kingdom"):
            return None
        struct.kingdom = irmng_charter_kingdom(cur["kingdom"])

        struct.taxon.name = cur["scientificname"]
        struct.taxon.rank = irmng_to_wp_rank(cur["rank"])
        struct.taxon.author = format_author(cur.get("authority"))
        if cur.get("isExtinct"):
            struct.taxon.extinct = True

        struct.classification = "IRMNG"
        struct.classification_taxobox = "IRMNG"

        classification_tree = await adapter.classification_by_id(irmng_id)
        ranks: list[RankName] = []
        if classification_tree is not None:
            # the last one is the taxon itself
            chain = flatten_aphia_classification(classification_tree)[:-1]
            chain = filter_ancestors_above_kingdom(
                chain, cur["kingdom"], struct.kingdom in KINGDOMS_KEPT_IN_CHAIN
            )
            for node in chain:
                wp_rank = irmng_to_wp_rank(node.get("rank") or "")
                ranks.append(RankName(name=node["scientificname"], rank=wp_rank))
            ranks.reverse()
        struct.ranks = ranks

        vernaculars = await adapter.vernaculars_by_id(irmng_id)
        vernacular = groupe_par_langue(
            (v.get("language_code") or v.get("language"), v.get("vernacular")) for v in vernaculars
        )
        if vernacular:
            struct.vernacular["IRMNG"] = vernacular

        struct.original_publication = await citation_or_text(
            adapter.resolve_doi_citation, await adapter.original_description(irmng_id)
        )

        original_id = cur.get("originalNameUsageID")
        if original_id and original_id != irmng_id:
            basionym_record = await adapter.record_by_id(original_id)
            if basionym_record is not None:
                struct.basionym = Basionym(
                    name=basionym_record["scientificname"],
                    author=format_author(basionym_record.get("authority")),
                    source="IRMNG",
                )

        async def fetch_synonyms(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.synonyms_by_id(irmng_id, offset=offset)
            items = [
                RankName(
                    name=s["scientificname"],
                    author=format_author(s.get("authority")),
                    rank=irmng_to_wp_rank(s["rank"]),
                )
                for s in page
            ]
            return items, len(page), len(page) < PAGE_SIZE

        synonyms, _ = await collect_pages(
            fetch_synonyms, start_offset=1, limit=as_limit(options.list_limit)
        )
        if synonyms:
            struct.synonyms = SynonymList(items=synonyms, source="IRMNG")

        async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.children_by_id(irmng_id, offset=offset)
            items = [
                RankName(
                    name=c["scientificname"],
                    author=format_author(c.get("authority")),
                    rank=irmng_to_wp_rank(c["rank"]),
                    extinct=bool(c.get("isExtinct")) or None,
                )
                for c in page
                # synonyms, uncertain and nomen dubium excluded:
                # explicit REST filter
                if c.get("status") == "accepted"
            ]
            return items, len(page), len(page) < PAGE_SIZE

        subtaxa, _ = await collect_pages(
            fetch_children, start_offset=1, limit=as_limit(options.list_limit)
        )
        if subtaxa:
            struct.subtaxa = SubTaxonList(items=subtaxa, source="IRMNG")

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{IRMNG}} template."""
        data = struct.links.get("irmng")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(
            data["name"], data.get("rank", struct.taxon.rank), struct.kingdom
        )
        if author := data.get("author"):
            target += " " + author
        extinct = "† " if data.get("extinct") else ""
        post = ""
        if data.get("synonym"):
            post = " <small>(non valide)</small>"
        return f"{{{{IRMNG | {data['id']} | {extinct}{target} | consulté le={cdate} }}}}{post}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the IRMNG page."""
        return simple_debug_link(
            struct, "irmng", "https://www.irmng.org/aphia.php?p=taxdetails&id={id}", "IRMNG"
        )


register_module(IrmngModule)
