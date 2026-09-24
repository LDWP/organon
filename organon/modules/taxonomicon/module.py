"""The Taxonomicon module (Systema Naturae 2000).

Enrichment only (`can_classify=False`): reuses the rank already known
from the main classification, as `organon.modules.oepp` does, since the
site gives no structured rank to scrape (see adapter.py).

Keeps only "Valid" matches (in the site's Systema Naturae 2000
classification, excluding "nom. inval." entries) whose name equals the
requested taxon, like `organon.modules.eflora`. The full author needs a
second call to the nomenclature page, like `oepp`.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.taxonomicon.adapter import TaxonomiconAdapter


class TaxonomiconModule(TaxonomyModule):
    """The Taxonomicon module."""

    meta = ModuleMeta(
        id="taxonomicon", can_classify=False, can_render_external_link=True, domains="all"
    )

    def __init__(self, adapter: TaxonomiconAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or TaxonomiconAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from The Taxonomicon."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        hits = await self._adapter.search(taxon)
        match = next((hit for hit in hits if hit[0] == "Valid" and hit[2] == taxon), None)
        if match is None:
            return None
        _, taxon_id, _ = match

        blob: LinkEntry = {"id": taxon_id, "name": taxon}
        author = await self._adapter.author_citation(taxon_id)
        if author:
            blob["author"] = format_author(author)

        struct.links["taxonomicon"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{Taxonomicon}} template."""
        data = struct.links.get("taxonomicon")
        if not data:
            return None
        cdate = retrieval_dates()
        name = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            name += " " + author
        return f"{{{{Taxonomicon | {data['id']} | {name} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the Taxonomicon page."""
        return simple_debug_link(
            struct,
            "taxonomicon",
            "http://taxonomicon.taxonomy.nl/TaxonTree.aspx?id={id}",
            "Taxonomicon",
        )


register_module(TaxonomiconModule)
