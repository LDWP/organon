"""CoL (Catalogue of Life) module: full classification.

Synonyms, sub-taxa and vernacular names too; a classification source in
its own right (`can_classify=True`), selectable like GBIF, ITIS and
WoRMS.

It queries only ChecklistBank dataset `3LXR` (Extended Release, see
`organon.modules.col_xr.adapter`) rather than `3LR` (the plain COL
release, the old merged module): the XR is a superset of the COL, and
`catalogueoflife.org/data/taxon/{id}` resolves both families of ids, so
there is no need to query 3LR apart or to tell where an id comes from
before building {{CatalogueofLife}}.

Accepted risk of the merge: unlike the old CoL module, it no longer
builds a list of records for an unresolved homonymy (e.g. *Morus* L.
(Plantae) and *Morus* Vieillot (Animalia), both "accepted" in 3LXR). It
keeps one record, disambiguated by kingdom when `struct.domain` is
known, then by record quality (see `select_col_xr_candidate`) when
several remain tied. Seen on cross-kingdom homonyms 3LXR leaves
unresolved (Toxoplasma gondii) and on non-deduplicated duplicates within
a kingdom (Escherichia coli). Judged rare beyond these cases.

Makes no HTTP call itself; see `organon.modules.col_xr.adapter`.
"""

from __future__ import annotations

import html as _html
from functools import partial

from organon.core.config import GenerateOptions
from organon.core.domains import kingdom_from_classification
from organon.core.langues import groupe_par_langue
from organon.core.models import (
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.lookup import (
    resolve_col_xr_matches,
    select_col_xr_candidate,
    strip_subgenus_before_epithet,
)
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.common import (
    as_limit,
    checklistbank_accepted_name,
    collect_pages,
    follow_synonym,
    format_author,
    simple_debug_link,
)


def _kingdom_index(classification: list[dict]) -> int | None:
    """Return the index of the kingdom in a classification, or None."""
    return next((i for i, c in enumerate(classification) if c.get("rank") == "kingdom"), None)


class ColModule(TaxonomyModule):
    """CoL module."""

    meta = ModuleMeta(
        id="col",
        can_classify=True,
        can_render_external_link=True,
        domains="all",
        # Default classification against GBIF (priority 200 formerly):
        # GBIF classifies only with the raw fields of its legacy
        # Backbone Taxonomy, never corrected by CoL XR beyond a missing
        # rank (see gbif/module.py). When both succeed and contradict,
        # the CoL XR record is the most up to date.
        priority=999,
        is_default_classification=True,
    )

    def __init__(self, adapter: ColXrAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or ColXrAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from the Catalogue of Life."""
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        """Collect with a synonym hop count."""
        adapter = self._adapter

        candidates = await resolve_col_xr_matches(adapter, struct.taxon.name)
        if not candidates:
            return None

        accepted = [r for r in candidates if r["usage"]["status"] == "accepted"]
        cur = select_col_xr_candidate(accepted, struct.domain)
        if cur is None:
            if not options.follow_synonyms:
                return None
            cur = select_col_xr_candidate(candidates, struct.domain)
            if cur is None:  # candidates is non-empty (guard above): never reached in practice
                return None

        usage = cur["usage"]
        name = usage["name"]
        taxon_id = cur["id"]

        struct.links["col"] = {
            "id": taxon_id,
            "name": name["scientificName"],
            "author": format_author(name.get("authorship")),
            "rank": col_xr_to_wp_rank(name.get("rank", "")),
            **({"extinct": usage["extinct"]} if "extinct" in usage else {}),
        }

        if not is_classification:
            # Same as gbif/module.py: the "classification" chain is
            # already in the search response, no extra call. See
            # RankInconsistency; not set when classifying, where
            # `struct.ranks` already covers these ranks for the winning
            # module.
            for ancestor in cur.get("classification", []):
                ancestor_rank = col_xr_to_wp_rank(ancestor.get("rank", ""))
                if ancestor_rank == "famille" and ancestor.get("name"):
                    struct.links["col"]["detected_family"] = ancestor["name"]
                elif ancestor_rank == "ordre" and ancestor.get("name"):
                    struct.links["col"]["detected_order"] = ancestor["name"]

        is_synonym = usage["status"] == "synonym"
        # Nomenclatural status of this very record (see
        # RankInconsistency), set before the redirect below, as in
        # gbif/module.py.
        struct.links["col"]["detected_status"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            handled, result = await follow_synonym(
                struct,
                "col",
                is_classification,
                options,
                hop,
                partial(checklistbank_accepted_name, usage),
                lambda next_hop: self._collect(struct, is_classification, options, hop=next_hop),
            )
            if handled:
                return result
            # follow_synonyms is off: the classification is built from
            # this synonym rather than the accepted taxon.

        if not is_classification:
            return struct

        struct.taxon.author = format_author(name.get("authorship"))
        struct.taxon.rank = col_xr_to_wp_rank(name.get("rank", ""))
        if "extinct" in usage:
            struct.taxon.extinct = usage["extinct"]
        # Without the subgenus CoL inserts ("Mus (Mus) musculus"):
        # enrichment modules search by this name, and no other source
        # indexes it so.
        struct.taxon.name = strip_subgenus_before_epithet(name["scientificName"].strip())
        struct.classification = "CatalogueofLife"
        struct.classification_taxobox = "COL"

        classification = cur.get("classification", [])
        idx = _kingdom_index(classification)
        if idx is None:
            return None
        struct.kingdom = kingdom_from_classification(classification)
        if not struct.kingdom:
            return None

        # `classification` goes from the root (domain) to the requested
        # taxon included (last element, same id as `taxon_id`). Drop
        # everything at or above the kingdom (as WRMS and IRMNG, see
        # `filter_ancestors_above_kingdom`) and the taxon's own entry,
        # then reverse to the nearest-first order of `struct.ranks`.
        struct.ranks = [
            RankName(
                name=c["name"],
                rank=col_xr_to_wp_rank(c.get("rank", "")),
                author=format_author(c.get("authorship")),
            )
            for c in reversed(classification[idx + 1 :])
            if c.get("id") != taxon_id
        ]

        async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.children_page(taxon_id, offset)
            raw = page.get("result", [])
            out = []
            for c in raw:
                # A missing "rank" (malformed record) is treated as
                # "unranked": same lack of usable information, same
                # exclusion from the sub-taxa list.
                if c.get("rank", "unranked") == "unranked" or c.get("status") != "accepted":
                    continue
                out.append(
                    RankName(
                        name=c["name"],
                        rank=col_xr_to_wp_rank(c["rank"]),
                        author=format_author(c.get("authorship")),
                        # ChecklistBank flags extinction with a leading
                        # "†" in the HTML label, not a structured field
                        # on this endpoint (unlike /taxon/{id}).
                        extinct=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        items, truncated = await collect_pages(fetch_children, limit=as_limit(options.list_limit))
        if items:
            struct.subtaxa = SubTaxonList(
                items=items, source="CatalogueofLife", truncated=truncated
            )

        vernacular = groupe_par_langue(
            (v.get("language"), _html.unescape(v["name"])) for v in cur.get("vernacularNames", [])
        )
        if vernacular:
            struct.vernacular["CatalogueofLife"] = vernacular

        syn = await adapter.synonyms(taxon_id)
        synonyms = []
        for entry in [*syn.get("homotypic", []), *syn.get("heterotypic", [])]:
            sname = entry.get("name") or {}
            if not sname.get("scientificName"):
                continue
            synonyms.append(
                RankName(
                    name=sname["scientificName"],
                    author=format_author(sname.get("authorship")),
                    rank=col_xr_to_wp_rank(sname.get("rank", "")),
                )
            )
        if synonyms:
            struct.synonyms = SynonymList(
                items=synonyms, source="CatalogueofLife", truncated=False
            )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{CatalogueofLife}} template."""
        data = struct.links.get("col")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(
            data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        if author := data.get("author"):
            target += " " + author
        extinct_param = " | éteint=oui" if data.get("extinct") else ""
        synonym_flag = " | nv" if data.get("synonym") else ""
        return (
            f"{{{{CatalogueofLife | {data['id']} | {target}{extinct_param}{synonym_flag} | "
            f"consulté le={cdate} }}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the CoL page."""
        return simple_debug_link(
            struct, "col", "https://www.catalogueoflife.org/data/taxon/{id}", "CoL"
        )


register_module(ColModule)
