"""FishBase, via its WoRMS-derived ChecklistBank export (1010)."""

from organon.core.models import Struct
from organon.core.registry import ModuleMeta, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.checklistbank import ChecklistBankModule


class FishbaseModule(ChecklistBankModule):
    """FishBase module, with templates for genera and orders."""

    meta = ModuleMeta(
        id="fishbase", can_classify=True, can_render_external_link=True, domains=["poisson"]
    )
    dataset_id = "1010"  # alias "WoRMS FishBase", resynced 2026-09-02
    label = "FishBase"
    site_name = "FishBase"
    link_source = "name"

    def render_bioref(self, struct: Struct) -> str | None:
        """Render a FishBase template for genera and orders."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data:
            return None
        rank = data.get("rank") or struct.taxon.rank
        date = retrieval_dates()
        suffix = " <small>(non valide)</small>" if data.get("synonym") else ""
        if rank == "genre":
            return f"{{{{FishBase genre | {data['name']} | consulté le={date} }}}}{suffix}"
        if rank == "ordre":
            author = f" | {data['author']}" if data.get("author") else ""
            return f"{{{{FishBase ordre | {data['name']}{author} | consulté le={date} }}}}{suffix}"
        # The other ranks have no numeric FishBase code since the export
        # moved to Aphia/WoRMS.
        return super().render_bioref(struct)


register_module(FishbaseModule)
