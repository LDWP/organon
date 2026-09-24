"""DORIS module (doris.ffessm.fr): enrichment only.

`can_classify=False`: the site gives no usable classification, only a
simplified grouping by icon ("DORIS group"). See adapter.py for the HTML
search used in the absence of a public API.

Domain restricted to the underwater fauna and flora the site covers
(animal, algae, aquatic plants, protists; no bacteria, fungi, archaea or
viruses).
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.doris.adapter import LEGACY_FICHE_URL, DorisAdapter


class DorisModule(TaxonomyModule):
    """DORIS module."""

    meta = ModuleMeta(
        id="doris",
        can_classify=False,
        can_render_external_link=True,
        domains=["animal", "algue", "végétal", "protiste"],
    )

    def __init__(self, adapter: DorisAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or DorisAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the DORIS page of the taxon."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        hit = await self._adapter.search(taxon)
        if hit is None:
            return None
        species_id, common_name = hit

        struct.links["doris"] = {"id": species_id, "name": taxon, "common_name": common_name}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{DORIS}} template."""
        data = struct.links.get("doris")
        if not data:
            return None
        cdate = retrieval_dates()
        description = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if struct.taxon.resolved_author:
            description += f" {struct.taxon.resolved_author}"
        return f"{{{{DORIS | {data['id']} | {description} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the DORIS page."""
        data = struct.links.get("doris")
        if not data:
            return None
        url = f"{LEGACY_FICHE_URL}?fiche_numero={data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>DORIS</a>"


register_module(DorisModule)
