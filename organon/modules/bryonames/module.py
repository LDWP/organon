"""Bryonames, bryophyte classification (dataset 170394)."""

from urllib.parse import quote

from organon.core.models import LinkEntry
from organon.core.registry import ModuleMeta, register_module
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


register_module(BryonamesModule)
