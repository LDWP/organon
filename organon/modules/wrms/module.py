"""WoRMS module: classification, synonyms, sub-taxa, vernacular names.

Through the REST API (see adapter.py).

Synonym following uses `valid_AphiaID` to fetch the accepted taxon
record directly by id, with no new text search.

The original publication has no structured REST field: it is scraped
from the HTML detail page, the one exception to "REST only".
`citations.build_citation` then tries to replace that raw text with a
structured citation when a DOI or BHL link is found, silently falling
back on the raw text.
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
from organon.modules.common import (
    as_limit,
    collect_pages,
    filter_ancestors_above_kingdom,
    flatten_aphia_classification,
    follow_synonym,
    format_author,
    simple_debug_link,
)
from organon.modules.wrms.adapter import WrmsAdapter
from organon.modules.wrms.citations import build_citation
from organon.modules.wrms.ranks import (
    KINGDOMS_KEPT_IN_CHAIN,
    wrms_charter_kingdom,
    wrms_to_wp_rank,
)

# Page size of the WoRMS REST API (fixed by the service).
PAGE_SIZE = 50


class WrmsModule(TaxonomyModule):
    """WoRMS module."""

    meta = ModuleMeta(
        id="wrms", can_classify=True, can_render_external_link=True, domains="all", priority=996
    )

    def __init__(self, adapter: WrmsAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or WrmsAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from WoRMS."""
        results = await self._adapter.records_by_name(
            struct.taxon.name, marine_only=options.marine_only
        )
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
        aphia_id = cur["AphiaID"]

        wrms_link: LinkEntry = {
            "id": aphia_id,
            "name": cur["scientificname"],
            "rank": wrms_to_wp_rank(cur["rank"]),
        }
        if cur.get("authority"):
            wrms_link["author"] = format_author(cur["authority"])
        if cur.get("isExtinct"):
            wrms_link["extinct"] = True
        if not is_classification and cur.get("kingdom"):
            # Kingdom signal detected with no extra call: "kingdom" is
            # already in the `records_by_name` response. See
            # KingdomInconsistency.
            detected_kingdom = wrms_charter_kingdom(cur["kingdom"])
            if detected_kingdom:
                wrms_link["detected_kingdom"] = detected_kingdom
        struct.links["wrms"] = wrms_link

        if cur.get("isTerrestrial"):
            # Takes precedence over isMarine: an amphibious or coastal
            # taxon is not "marine only", so it must not get {{Portail
            # biologie marine}} (see portails.yaml).
            struct.habitat = "terrestre"
        elif cur.get("isMarine"):
            struct.habitat = "marin"

        is_synonym = cur.get("valid_AphiaID") is not None and cur["valid_AphiaID"] != aphia_id
        if is_synonym:
            accepted: dict | None = None

            async def resolve_accepted() -> str | None:
                nonlocal accepted
                accepted = await adapter.record_by_id(cur["valid_AphiaID"])
                return accepted["scientificname"] if accepted is not None else None

            async def recurse_accepted(next_hop: int) -> Struct | None:
                assert accepted is not None  # follow_synonym recurses only once resolved
                return await self._process(
                    struct, accepted, is_classification, options, hop=next_hop
                )

            handled, result = await follow_synonym(
                struct,
                "wrms",
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
        struct.kingdom = wrms_charter_kingdom(cur["kingdom"])

        struct.taxon.name = cur["scientificname"]
        struct.taxon.rank = wrms_to_wp_rank(cur["rank"])
        struct.taxon.author = format_author(cur.get("authority"))
        if cur.get("isExtinct"):
            struct.taxon.extinct = True

        struct.classification = "WRMS"
        struct.classification_taxobox = "WoRMS"

        classification_tree = await adapter.classification_by_id(aphia_id)
        ranks: list[RankName] = []
        if classification_tree is not None:
            # the last one is the taxon itself
            chain = flatten_aphia_classification(classification_tree)[:-1]
            chain = filter_ancestors_above_kingdom(
                chain, cur["kingdom"], struct.kingdom in KINGDOMS_KEPT_IN_CHAIN
            )
            for node in chain:
                wp_rank = wrms_to_wp_rank(node.get("rank") or "")
                ranks.append(RankName(name=node["scientificname"], rank=wp_rank))
            ranks.reverse()
        struct.ranks = ranks

        vernaculars = await adapter.vernaculars_by_id(aphia_id)
        vernacular = groupe_par_langue(
            (v.get("language_code") or v.get("language"), v.get("vernacular")) for v in vernaculars
        )
        if vernacular:
            struct.vernacular["WRMS"] = vernacular

        raw_original = await adapter.original_description(aphia_id)
        struct.original_publication = await build_citation(adapter, raw_original)

        original_id = cur.get("originalNameUsageID")
        if original_id and original_id != aphia_id:
            basionym_record = await adapter.record_by_id(original_id)
            if basionym_record is not None:
                struct.basionym = Basionym(
                    name=basionym_record["scientificname"],
                    author=format_author(basionym_record.get("authority")),
                    source="WRMS",
                )

        async def fetch_synonyms(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.synonyms_by_id(aphia_id, offset=offset)
            items = [
                RankName(
                    name=s["scientificname"],
                    author=format_author(s.get("authority")),
                    rank=wrms_to_wp_rank(s["rank"]),
                )
                for s in page
            ]
            return items, len(page), len(page) < PAGE_SIZE

        synonyms, _ = await collect_pages(
            fetch_synonyms, start_offset=1, limit=as_limit(options.list_limit)
        )
        if synonyms:
            struct.synonyms = SynonymList(items=synonyms, source="WRMS")

        async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.children_by_id(
                aphia_id, marine_only=options.marine_only, offset=offset
            )
            items = [
                RankName(
                    name=c["scientificname"],
                    author=format_author(c.get("authority")),
                    rank=wrms_to_wp_rank(c["rank"]),
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
            struct.subtaxa = SubTaxonList(items=subtaxa, source="WRMS")

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{WRMS}} or {{WRMS espèce}} template."""
        data = struct.links.get("wrms")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        if struct.taxon.rank in ("espèce", "sous-espèce"):
            template = "WRMS espèce"
            name = data["name"]
        else:
            template = "WRMS"
            name = wp_apply_italics(
                data["name"], data.get("rank", struct.taxon.rank), struct.kingdom
            )
        extinct = "éteint=oui | " if data.get("extinct") else ""
        author = data.get("author", "")
        return (
            f"{{{{{template} | {data['id']} | {name} | {author} | {extinct}consulté le={cdate}}}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the WoRMS page."""
        return simple_debug_link(
            struct, "wrms", "https://www.marinespecies.org/aphia.php?p=taxdetails&id={id}", "WRMS"
        )


register_module(WrmsModule)
