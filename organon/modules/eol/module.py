"""EOL module (Encyclopedia of Life): enrichment only.

`can_classify=False`: reuses the rank already known from the main
classification rather than deriving one from EOL.

The author is extracted from `scientificName` (the full scientific name
followed by the author, e.g. "Gadus morhua Linnaeus, 1758") by removing
the known name.

EOL contributes no French vernacular names: it copies them from Wikidata
(a mirror), which creates loops propagating Wikidata errors to EOL and
then to Wikispecies and French Wikipedia (see ticket #39 on the
Biologie/Organon wiki, "Épilobe-mollet" for Epilobium parviflorum).
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.eol.adapter import EolAdapter


class EolModule(TaxonomyModule):
    """EOL module."""

    meta = ModuleMeta(id="eol", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: EolAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or EolAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the EOL page of the taxon."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        results = await self._adapter.search(taxon)
        match = next((r for r in results if r.get("title") == taxon), None)
        if match is None:
            return None

        blob: LinkEntry = {"id": match["id"], "name": taxon}

        page = await self._adapter.page(match["id"])
        if page is not None:
            scientific_name = page.get("scientificName") or ""
            if scientific_name.startswith(taxon):
                author = scientific_name[len(taxon) :].strip()
                if author:
                    blob["author"] = format_author(author)

        struct.links["eol"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{EOL}} template."""
        data = struct.links.get("eol")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            target += " " + author
        return f"{{{{EOL | {data['id']} | {target} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the EOL page."""
        return simple_debug_link(struct, "eol", "https://eol.org/fr/pages/{id}", "EoL")


register_module(EolModule)
