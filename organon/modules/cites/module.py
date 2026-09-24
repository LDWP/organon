"""CITES module: enrichment only (no classification).

It feeds `{{Taxobox CITES}}` (see `sections.render_taxobox`) and the
French vernacular names.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.langues import groupe_par_langue
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.cites.adapter import CitesAdapter
from organon.modules.common import format_author, simple_debug_link


class CitesModule(TaxonomyModule):
    """CITES module."""

    meta = ModuleMeta(id="cites", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: CitesAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or CitesAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the CITES listing of the taxon."""
        if is_classification:
            return None  # CITES never provides a classification

        candidates = await self._adapter.autocomplete(struct.taxon.name)
        match = next((c for c in candidates if c.get("full_name") == struct.taxon.name), None)
        if match is None:
            return None

        detail = await self._adapter.taxon_concept(match["id"])
        if detail is None or not detail.get("cites_listings"):
            return None

        listing = detail["cites_listings"][0]
        struct.links["cites"] = {
            "id": match["id"],
            "name": detail["full_name"],
            "author": format_author(detail.get("author_year")),
            "appendix": listing.get("species_listing_name"),
            "date": listing.get("effective_at_formatted"),
        }

        vernacular = groupe_par_langue(
            (cn.get("lang"), name)
            for cn in detail.get("common_names") or []
            for name in (cn.get("names") or "").split(", ")
        )
        if vernacular:
            struct.vernacular["CITES espèce"] = vernacular

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{CITES species+}} template."""
        data = struct.links.get("cites")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        author = data.get("author") or ""
        return (
            f"{{{{CITES species+ | {data['id']} | {target} | {author} | consulté le={cdate} }}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the Species+ page."""
        return simple_debug_link(
            struct,
            "cites",
            "https://www.speciesplus.net/#/taxon_concepts/{id}/legal",
            "CITES species+",
        )


register_module(CitesModule)
