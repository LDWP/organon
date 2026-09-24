"""ICTV module: reference classification for the `virus` domain.

Pure reading of the embedded dataset (adapter.py). No synonyms (the VMR
export has none) nor author (ICTV does not use the classical author
citation).

`ICTV_ID` exists only at species rank in the source dataset:
`render_bioref` and `debug_link` give a link only for that rank, None
otherwise. A dataset limit, not an oversight.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import simple_debug_link
from organon.modules.ictv.adapter import IctvAdapter
from organon.modules.ictv.ranks import ictv_to_wp_rank


class IctvModule(TaxonomyModule):
    """ICTV module."""

    meta = ModuleMeta(
        id="ictv", can_classify=True, can_render_external_link=True, domains=["virus"]
    )

    def __init__(self, adapter: IctvAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or IctvAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from the ICTV dataset."""
        record = self._adapter.find(struct.taxon.name)
        if record is None:
            return None

        rank = ictv_to_wp_rank(record.rang_colonne)
        ictv_link: LinkEntry = {"name": record.nom, "rank": rank}
        if record.ictv_id:
            ictv_link["id"] = record.ictv_id
        struct.links["ictv"] = ictv_link

        if not is_classification:
            return struct

        struct.kingdom = "virus"
        struct.classification = "ICTV"
        struct.classification_taxobox = "ICTV"
        struct.taxon = TaxonInfo(name=record.nom, rank=rank)

        struct.ranks = [
            RankName(name=name, rank=ictv_to_wp_rank(column))
            for column, name in reversed(record.ancestors[:-1])
        ]

        children = self._adapter.children_of(record.nom)
        if children:
            struct.subtaxa = SubTaxonList(
                items=[
                    RankName(name=name, rank=ictv_to_wp_rank(column)) for column, name in children
                ],
                source="ICTV",
            )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{ICTV}} template (species only)."""
        data = struct.links.get("ictv")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        name = wp_apply_italics(data["name"], data.get("rank", struct.taxon.rank), struct.kingdom)
        return f"{{{{ICTV | {data['id']} | {name} |  | consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the ICTV page."""
        return simple_debug_link(struct, "ictv", "https://ictv.global/id/{id}", "ICTV")


register_module(IctvModule)
