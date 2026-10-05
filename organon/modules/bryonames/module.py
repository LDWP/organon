"""Bryonames, bryophyte classification (dataset 170394)."""

from urllib.parse import quote

from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.checklistbank import ChecklistBankModule


class BryonamesModule(ChecklistBankModule):
    """Bryonames module."""

    meta = ModuleMeta(
        id="bryonames", can_classify=True, can_render_external_link=True, domains=["végétal"]
    )
    dataset_id = "170394"  # alias "Bryonames", DOI 10.48580/d8zmp, permanent
    label = "Bryonames"
    site_name = "Bryonames"
    # The classification starts at "subkingdom", so the kingdom is
    # fixed.
    kingdom = "végétal"

    def _page_url(self, data: LinkEntry) -> str:
        """Return the Bryonames nomenclator page of the taxon."""
        # `name.link` is a Tropicos URL, and the ChecklistBank page sits
        # behind an anti-bot check. `?group=` works for families and
        # genera; species pages are behind a Cloudflare challenge that
        # blocks automated checks, so they are unverified.
        return f"https://www.bryonames.org/nomenclator?group={quote(data['name'])}"

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{Bryonames}} template."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data:
            return None
        display = wp_apply_italics(
            data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        if author := data.get("author"):
            display += " " + author
        suffix = " | nv=1" if data.get("synonym") else ""
        return (
            f"{{{{Bryonames | {data['name']} | {display} "
            f"| consulté le={retrieval_dates()}{suffix} }}}}"
        )


register_module(BryonamesModule)
