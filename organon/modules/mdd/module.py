"""Mammal Diversity Database (ChecklistBank dataset 9802)."""

from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.checklistbank import ChecklistBankModule

_HIGHER_RANKS = {"ordre", "famille", "genre"}


class MddModule(ChecklistBankModule):
    """Mammal Diversity Database module, with MDD templates."""

    meta = ModuleMeta(
        id="mdd", can_classify=True, can_render_external_link=True, domains=["mammifère"]
    )
    dataset_id = "9802"  # "The Mammal Diversity Database", resynced 2025-04-08
    label = "MDD"
    site_name = "Mammal Diversity Database"

    def _extra_links(self, current: dict) -> LinkEntry:
        """Return the genus and epithet of the record."""
        name = current["usage"]["name"]
        return {"genus": name.get("genus"), "epithet": name.get("specificEpithet")}

    def _page_url(self, data: LinkEntry) -> str:
        """Return the MDD site URL of the taxon."""
        # checklistbank.org sits behind an anti-bot check, so cite the
        # MDD site itself.
        return f"https://www.mammaldiversity.org/taxon/{data['id']}"

    def render_bioref(self, struct: Struct) -> str | None:
        """Render an MDD template for known ranks, else the default."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data:
            return None
        rank = data.get("rank") or struct.taxon.rank
        date = retrieval_dates()
        suffix = " <small>(non valide)</small>" if data.get("synonym") else ""
        if rank in _HIGHER_RANKS:
            return f"{{{{MDDsup | {rank} | {data['name']} | consulté le={date} }}}}{suffix}"
        if rank in ("espèce", "sous-espèce") and data.get("genus") and data.get("epithet"):
            target = wp_apply_italics(data["name"], rank, struct.kingdom)
            if author := data.get("author"):
                target += " " + author
            return (
                f"{{{{MDD | {data['genus']} | {data['epithet']} | {data['id']} | {target} "
                f"| consulté le={date} }}}}{suffix}"
            )
        return super().render_bioref(struct)


register_module(MddModule)
