"""LPSN (List of Prokaryotic names with Standing in Nomenclature).

Reference classification for the bacteria, archaea and prokaryote
domains.

Synonym following: `lpsn_correct_name_id` in each record points to the
accepted name's id.

Classification: each record carries only its immediate parent
(`lpsn_parent_id`), so `_walk_ancestors` climbs one level at a time up
to the domain (Bacteria or Archaea), which gives `struct.kingdom` and is
excluded from `struct.ranks`.

The nomenclatural type (`nomenclatural_type_id`) feeds
`struct.type_taxon`: this is the only module filling that field.

Sub-taxa: `flexible_search({"lpsn_parent_id": id})` finds the direct
children, fetched in batches; synonyms among them are excluded.

Out of scope, an API limit: `struct.synonyms`, and historical names
never recorded under their genus; no cross-source correction (see
`organon.modules.gbif.module`).

Original publication: see `citations.build_citation`.
"""

from __future__ import annotations

import asyncio

from organon.core.auth_settings import get_auth_settings
from organon.core.config import GenerateOptions
from organon.core.models import (
    Basionym,
    LinkEntry,
    RankName,
    Struct,
    SubTaxonList,
    TypeTaxon,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import as_limit, collect_pages, follow_synonym, format_author
from organon.modules.lpsn import citations
from organon.modules.lpsn.adapter import LpsnAdapter
from organon.modules.lpsn.ranks import lpsn_lookup_kingdom, lpsn_to_wp_rank

LPSN_WEBSITE_BASE = "https://lpsn.dsmz.de"
# `fetch` batch size when paging children: small enough to keep
# `fetch/id1;id2;...` under URL length limits.
CHILDREN_PAGE_SIZE = 50


def _slug_from_record(cur: dict) -> str | None:
    """Return the {{LPSN}} template id (e.g. "hyphomonas-rosenbergii").

    `lpsn_address` holds the permanent DOI link, so it does not do.
    """
    monomial = cur.get("monomial")
    if not monomial:
        return None
    epithets = [monomial]
    for key in ("species_epithet", "subspecies_epithet"):
        epithet = cur.get(key)
        if epithet:
            epithets.append(epithet)
    return "-".join(epithets).lower()


class LpsnModule(TaxonomyModule):
    """LPSN module."""

    meta = ModuleMeta(
        id="lpsn",
        can_classify=True,
        can_render_external_link=True,
        domains=["bactérie", "archaea", "procaryote"],
    )

    def __init__(self, adapter: LpsnAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or LpsnAdapter()

    def is_configured(self) -> bool:
        """Return True if the LPSN credentials are set."""
        settings = get_auth_settings()
        return bool(settings.lpsn_username and settings.lpsn_password)

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from LPSN."""
        ids = await self._adapter.advanced_search(taxon_name=struct.taxon.name)
        if not ids:
            return None
        records = await self._adapter.fetch(ids)
        exact = [r for r in records if r.get("full_name") == struct.taxon.name]
        if not exact:
            return None
        # Prefer the accepted name among several exact matches (rare,
        # e.g. a combination homonym): a missing `lpsn_correct_name_id`,
        # or one equal to its own id, means accepted.
        cur = next(
            (r for r in exact if r.get("lpsn_correct_name_id") in (None, r.get("id"))), exact[0]
        )
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
        lpsn_id = cur["id"]
        rank = lpsn_to_wp_rank(cur.get("category"))

        entry: LinkEntry = {"name": cur.get("full_name") or struct.taxon.name, "rank": rank}
        category = cur.get("category")
        slug = _slug_from_record(cur)
        if slug and category:
            entry["id"] = slug
            entry["url"] = f"{LPSN_WEBSITE_BASE}/{category}/{slug}"
        else:
            # Fall back on the LPSN record number (always present) when
            # the record lacks what is needed for the friendly slug or
            # the URL category: `/taxon/{id}` does not depend on the
            # rank.
            entry["id"] = lpsn_id
            entry["url"] = f"{LPSN_WEBSITE_BASE}/taxon/{lpsn_id}"
        if cur.get("authority"):
            entry["author"] = format_author(cur["authority"])
        struct.links["lpsn"] = entry

        correct_id = cur.get("lpsn_correct_name_id")
        is_synonym = correct_id is not None and correct_id != lpsn_id
        if is_synonym:
            accepted: dict | None = None

            async def resolve_accepted() -> str | None:
                nonlocal accepted
                assert correct_id is not None  # guaranteed by `is_synonym` above
                accepted = await adapter.fetch_one(correct_id)
                return (
                    accepted.get("full_name") or struct.taxon.name
                    if accepted is not None
                    else None
                )

            async def recurse_accepted(next_hop: int) -> Struct | None:
                assert accepted is not None  # follow_synonym recurses only once resolved
                return await self._process(
                    struct, accepted, is_classification, options, hop=next_hop
                )

            handled, result = await follow_synonym(
                struct,
                "lpsn",
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

        chain, domain_name = await self._walk_ancestors(cur)
        struct.kingdom = lpsn_lookup_kingdom(domain_name)
        if not struct.kingdom:
            return None

        struct.taxon.name = cur.get("full_name") or struct.taxon.name
        struct.taxon.rank = rank
        struct.taxon.author = format_author(cur.get("authority"))

        struct.classification = "LPSN"
        struct.classification_taxobox = "LPSN"

        # `_walk_ancestors` climbs from the requested taxon, so `chain`
        # is already nearest first, as struct.ranks expects.
        struct.ranks = [
            RankName(
                name=n["full_name"],
                rank=lpsn_to_wp_rank(n.get("category")),
                author=format_author(n.get("authority")),
            )
            for n in chain
            if n.get("full_name")
        ]

        struct.original_publication = await citations.build_citation(adapter, cur)

        async def fetch_basionyme() -> Basionym | None:
            basonym_id = cur.get("basonym_id")
            if not basonym_id or basonym_id == lpsn_id:
                return None
            basionym = await adapter.fetch_one(basonym_id)
            if basionym is None or not basionym.get("full_name"):
                return None
            return Basionym(
                name=basionym["full_name"],
                author=format_author(basionym.get("authority")),
                source="LPSN",
            )

        async def fetch_type_taxon() -> TypeTaxon | None:
            type_id = cur.get("nomenclatural_type_id")
            if not type_id:
                return None
            type_rec = await adapter.fetch_one(type_id)
            if type_rec is None or not type_rec.get("full_name"):
                return None
            return TypeTaxon(
                name=type_rec["full_name"],
                rank=lpsn_to_wp_rank(type_rec.get("category")),
                author=format_author(type_rec.get("authority")),
                source="LPSN",
            )

        async def fetch_subtaxa() -> SubTaxonList | None:
            child_ids = await adapter.flexible_search({"lpsn_parent_id": lpsn_id})
            if not child_ids:
                return None

            async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
                page_ids = child_ids[offset : offset + CHILDREN_PAGE_SIZE]
                records = await adapter.fetch(page_ids)
                items = [
                    RankName(
                        name=r["full_name"],
                        rank=lpsn_to_wp_rank(r.get("category")),
                        author=format_author(r.get("authority")),
                    )
                    for r in records
                    # Same acceptance test as `is_synonym`: a sub-taxon
                    # lists accepted names, not their synonyms.
                    if r.get("full_name") and r.get("lpsn_correct_name_id") in (None, r.get("id"))
                ]
                done = offset + CHILDREN_PAGE_SIZE >= len(child_ids)
                return items, len(page_ids), done

            subtaxa, truncated = await collect_pages(
                fetch_children, limit=as_limit(options.list_limit)
            )
            if not subtaxa:
                return None
            return SubTaxonList(items=subtaxa, source="LPSN", truncated=truncated)

        # Three independent blocks (basonym_id and type_id come from
        # `cur`, flexible_search from `lpsn_id`): run in parallel to
        # save round trips.
        struct.basionym, struct.type_taxon, struct.subtaxa = await asyncio.gather(
            fetch_basionyme(), fetch_type_taxon(), fetch_subtaxa()
        )

        return struct

    async def _walk_ancestors(self, cur: dict) -> tuple[list[dict], str | None]:
        """Climb `lpsn_parent_id` up to the domain, which is excluded.

        Return (chain nearest first, domain name or None if not
        reached).
        """
        chain: list[dict] = []
        node = cur
        while node.get("lpsn_parent_id"):
            parent = await self._adapter.fetch_one(node["lpsn_parent_id"])
            if parent is None:
                return chain, None
            if parent.get("category") == "domain":
                return chain, parent.get("full_name")
            chain.append(parent)
            node = parent
        return chain, None

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{LPSN}} template."""
        data = struct.links.get("lpsn")
        if not data or "id" not in data or not data.get("rank"):
            return None
        cdate = retrieval_dates()
        name = wp_apply_italics(data["name"], data["rank"], struct.kingdom)
        if data.get("author"):
            name = f"{name} {data['author']}"
        # The rank is always parameter 1; only {{{2}}} tells the numeric
        # id from the alphabetic slug, to build the URL
        # (/{english-rank}/{slug} or /taxon/{id}).
        return f"{{{{LPSN | {data['rank']} | {data['id']} | {name} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the LPSN page."""
        data = struct.links.get("lpsn")
        if not data or not data.get("url"):
            return None
        return f"<a href='{data['url']}' target='_blank' rel='noopener noreferrer'>LPSN</a>"


register_module(LpsnModule)
