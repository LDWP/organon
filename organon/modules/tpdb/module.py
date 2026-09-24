"""TPDB module (Paleobiology Database): enrichment only.

Rank and author come from a second call to `taxa/single.json` (see
adapter.py) after the initial search. The "invalid" status (`nv`,
recombination or synonym) is captured but unused by `render_bioref()`:
the `{{TPDB}}` template does not handle it.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.tpdb.adapter import TpdbAdapter
from organon.modules.tpdb.ranks import tpdb_to_wp_rank


class TpdbModule(TaxonomyModule):
    """TPDB module."""

    meta = ModuleMeta(id="tpdb", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: TpdbAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or TpdbAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from the Paleobiology Database."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        results = await self._adapter.search(taxon)
        if not results:
            return None

        # if several search entries share exactly this name, the last
        # one wins.
        record_id: str | None = None
        for r in results:
            if r.get("name") == taxon:
                record_id = r.get("record_id")
        if record_id is None:
            return None

        blob: LinkEntry = {"id": record_id, "name": taxon}

        detail = await self._adapter.taxon_by_name(taxon)
        if detail is not None:
            if detail.get("taxon_name"):
                blob["name"] = detail["taxon_name"]
            if detail.get("taxon_rank"):
                blob["rank"] = tpdb_to_wp_rank(detail["taxon_rank"])
            if detail.get("taxon_attr"):
                blob["author"] = format_author(detail["taxon_attr"])
            accepted_name = detail.get("accepted_name")
            if accepted_name and accepted_name != detail.get("taxon_name"):
                blob["invalid"] = True

        struct.links["tpdb"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{TPDB}} template."""
        data = struct.links.get("tpdb")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        name = wp_apply_italics(
            data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        if author := data.get("author"):
            name += " " + author
        return f"{{{{TPDB | {data['id']} | {name} | consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the TPDB page."""
        return simple_debug_link(
            struct, "tpdb", "https://paleobiodb.org/classic/basicTaxonInfo?taxon_no={id}", "TPDB"
        )


register_module(TpdbModule)
