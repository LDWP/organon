"""OEPP/EPPO module (Global Database, regulated organisms).

Pests, diseases and weeds. Enrichment only (`can_classify=False`).
Reuses the rank already known from the main classification: the EPPO
Global Database gives no usable structured rank.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.oepp.adapter import OeppAdapter


class OeppModule(TaxonomyModule):
    """OEPP/EPPO module."""

    meta = ModuleMeta(id="oepp", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: OeppAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or OeppAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon and its French names from EPPO."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        results = await self._adapter.search(taxon)
        match = next((r for r in results if r.get("f") == taxon), None)
        if match is None:
            return None

        blob: LinkEntry = {"id": match["e"], "name": taxon}

        detail = await self._adapter.taxon_detail(match["e"])
        if detail["auteur"]:
            blob["author"] = format_author(detail["auteur"])
        if detail["vernaculaire_fr"]:
            struct.vernacular["OEPP"] = {"fr": detail["vernaculaire_fr"]}

        struct.links["oepp"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{OEPP}} template."""
        data = struct.links.get("oepp")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        author = data.get("author") or ""
        return f"{{{{OEPP | {data['id']} | {target} | {author} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the EPPO page."""
        return simple_debug_link(struct, "oepp", "https://gd.eppo.int/taxon/{id}", "OEPP")


register_module(OeppModule)
