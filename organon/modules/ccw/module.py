"""Checklist of the Collembola of the World (dataset 2130)."""

from organon.core.models import RankName
from organon.core.registry import ModuleMeta, register_module
from organon.modules.checklistbank import ChecklistBankModule


class CcwModule(ChecklistBankModule):
    """Checklist of the Collembola of the World module."""

    meta = ModuleMeta(
        id="ccw", can_classify=True, can_render_external_link=True, domains=["animal"]
    )
    dataset_id = "2130"  # alias "Collembola.org", DOI 10.48580/d4kh, version Feb 2025
    label = "CCW"
    site_name = "Checklist of the Collembola of the World"
    # The dataset is Collembola only and its classification stops at
    # "class".
    fixed_chain = (
        RankName(name="Hexapoda", rank="sous-embranchement"),
        RankName(name="Arthropoda", rank="embranchement"),
    )
    # `usage.link` points to the group page on collembola.org, not to a
    # per-taxon page.
    link_source = "usage"


register_module(CcwModule)
