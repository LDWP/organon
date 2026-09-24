"""eFloras module (eFloras.org): enrichment only.

`can_classify=False`, plant domain. A species may have a record per
regional flora (North America, China, Pakistan), so `render_bioref`
returns a list, one `{{EFloras}}` per record found, like
`organon.modules.col` for Catalogue of Life.

The displayed name of each result must equal the requested taxon: the
eFloras.org search matches partially, so a genus-only query returns its
own record repeated per flora but could return related taxa for a more
ambiguous query.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.eflora.adapter import EfloraAdapter


class EfloraModule(TaxonomyModule):
    """eFloras module."""

    meta = ModuleMeta(
        id="eflora", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: EfloraAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or EfloraAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the eFloras records of the taxon."""
        if is_classification:
            return None

        taxon = struct.taxon.name
        hits = await self._adapter.search(taxon)
        matches = [(fid, tid) for fid, tid, name in hits if name == taxon]
        if not matches:
            return None

        struct.links["eflora"] = {"name": taxon, "ids": matches}
        return struct

    def render_bioref(self, struct: Struct) -> list[str] | None:
        """Render one {{EFloras}} template per record."""
        data = struct.links.get("eflora")
        if not data or not data.get("ids"):
            return None
        cdate = retrieval_dates()
        return [
            f"{{{{EFloras | {fid} | {tid} | {data['name']} | consulté le={cdate} }}}}"
            for fid, tid in data["ids"]
        ]

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug links to the eFloras records."""
        data = struct.links.get("eflora")
        if not data or not data.get("ids"):
            return None
        links = [
            f"<a href='http://www.efloras.org/florataxon.aspx?flora_id={fid}&taxon_id={tid}' "
            f"target='_blank' rel='noopener noreferrer'>eFlora ({fid})</a>"
            for fid, tid in data["ids"]
        ]
        return " ".join(links)


register_module(EfloraModule)
