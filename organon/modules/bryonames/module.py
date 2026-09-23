"""Bryonames, bryophyte classification (dataset 170394)."""

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
    link_source = "name"


register_module(BryonamesModule)
