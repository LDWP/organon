"""NCBI Taxonomy module: enrichment only.

`can_classify=False` (NCBI is explicitly discouraged as a taxonomic
reference): it only gives a cross id, reusing the name and rank already
known from the main classification rather than NCBI's own.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import simple_debug_link
from organon.modules.ncbi.adapter import NcbiAdapter


class NcbiModule(TaxonomyModule):
    """NCBI Taxonomy module."""

    meta = ModuleMeta(id="ncbi", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: NcbiAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or NcbiAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the NCBI id of the taxon."""
        if is_classification:
            return None

        taxid = await self._adapter.search_taxid(struct.taxon.name)
        if taxid is None:
            return None

        struct.links["ncbi"] = {"id": taxid, "name": struct.taxon.name, "rank": struct.taxon.rank}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{NCBI}} template."""
        data = struct.links.get("ncbi")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(
            data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        return f"{{{{NCBI | {data['id']} | {target} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the NCBI page."""
        return simple_debug_link(
            struct,
            "ncbi",
            "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={id}",
            "NCBI",
        )


register_module(NcbiModule)
