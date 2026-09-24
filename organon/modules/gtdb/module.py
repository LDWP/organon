"""GTDB module (Genome Taxonomy Database): identifier enrichment.

Id and link to the source page, through ChecklistBank dataset 2214.
Domain restricted to bacteria, archaea and prokaryotes, like
`organon.modules.lpsn.module`.

`can_classify=False` is deliberate, unlike Bryonames and GRIN: GTDB
gives provisional suffixed species names (e.g. "Escherichia
hormaechei_A") to uncultured genomes or cryptic groups with no published
Latin name, which are not available names under the ICNP. The dataset
documentation confirms it. LPSN stays the only classification source for
this domain (see `organon.modules.lpsn. module`); GTDB only brings a
link to the phylogenomic placement, never a name or hierarchy replacing
LPSN's.

The dataset only holds "accepted" records (GTDB has no notion of
synonymy), so no synonym following is needed.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.checklistbank import ChecklistBankAdapter
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.common import format_author


class GtdbModule(TaxonomyModule):
    """GTDB module."""

    meta = ModuleMeta(
        id="gtdb",
        can_classify=False,
        can_render_external_link=True,
        domains=["bactérie", "archaea", "procaryote"],
    )

    def __init__(self, adapter: ChecklistBankAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or ChecklistBankAdapter("2214")

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the GTDB record of the taxon."""
        candidates = await self._adapter.search(struct.taxon.name)
        exact = [
            r for r in candidates if r["usage"]["name"]["scientificName"] == struct.taxon.name
        ]
        cur = exact[0] if exact else None
        if cur is None:
            return None

        name = cur["usage"]["name"]
        struct.links["gtdb"] = {
            "id": cur["id"],
            "name": name["scientificName"],
            "author": format_author(name.get("authorship")),
            "rank": col_xr_to_wp_rank(name["rank"]),
            "link": name.get("link"),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render a {{Lien web}} citation to GTDB."""
        data = struct.links.get("gtdb")
        if not data or "id" not in data or not (url := data.get("link")):
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(
            data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        if author := data.get("author"):
            target += " " + author
        return (
            f"{{{{Lien web | langue=en | titre={target} | url={url} "
            f"| site=GTDB | consulté le={cdate} }}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the GTDB record."""
        data = struct.links.get("gtdb")
        if not data or "id" not in data or not (url := data.get("link")):
            return None
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>GTDB</a>"


register_module(GtdbModule)
