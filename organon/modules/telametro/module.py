"""TelaMétro module (Tela Botanica, BDTFX).

The BDTFX is the flora of metropolitan France. Enrichment only
(`can_classify=False`), plant domain. Reuses the name and rank already
known from the main classification (the BDTFX gives no rank translatable
to Wikipedia in this search).

Vernacular names come from a second call (`french_common_names`,
scraping the Ethnobotanique tab) rather than the Algolia `common_name`;
see `TelametroAdapter`. They feed `struct.other_names` (grouped by BDTFX
status), not `struct.vernacular`: the BDTFX qualifies each name with an
explicit status, which must not be lost by merging into the flat
`vernacular` list.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.telametro.adapter import TelametroAdapter


class TelametroModule(TaxonomyModule):
    """TelaMétro module."""

    meta = ModuleMeta(
        id="telametro", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: TelametroAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or TelametroAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon and its vernacular names from TelaMétro."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        hits = await self._adapter.search(taxon)

        match = None
        for hit in hits:
            bdtfx = hit.get("bdtfx")
            if not bdtfx:
                continue
            if (bdtfx.get("scientific_name") or "").strip() == taxon:
                match = bdtfx
                break
        if match is None:
            return None

        author = match.get("author") or ""
        year = match.get("year")
        if year:
            author = f"{author} {year}".strip()

        blob: LinkEntry = {"id": match["nomenclatural_number"], "name": taxon}
        if author:
            blob["author"] = format_author(author)
        struct.links["telametro"] = blob

        other_names = await self._adapter.french_common_names(match["nomenclatural_number"])
        if other_names:
            struct.other_names["Tela-métro"] = other_names

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{Tela-métro}} template."""
        data = struct.links.get("telametro")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        text = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            text += " " + author
        return f"{{{{Tela-métro | {data['id']} | {text} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the TelaMétro page."""
        return simple_debug_link(
            struct,
            "telametro",
            "https://www.tela-botanica.org/eflore/?referentiel=bdtfx&module=fiche&action=fiche"
            "&num_nom={id}&onglet=synthese",
            "TelaMétro",
        )


register_module(TelametroModule)
