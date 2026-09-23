"""A ChecklistBank module must be able to cite a page of the source's own site."""

import pytest

from organon.core.registry import ModuleMeta
from organon.modules.checklistbank import ChecklistBankModule


def _meta(**kwargs):
    return ModuleMeta(id="x", can_classify=True, domains=["animal"], **kwargs)


def test_dataset_without_source_page_url_is_rejected():
    with pytest.raises(TypeError):

        class _NoUrl(ChecklistBankModule):
            meta = _meta(can_render_external_link=True)
            dataset_id = "1"
            label = site_name = "X"


def test_module_not_rendering_external_link_is_rejected():
    with pytest.raises(TypeError):

        class _NoLink(ChecklistBankModule):
            meta = _meta(can_render_external_link=False)
            dataset_id = "1"
            label = site_name = "X"
            link_source = "usage"


def test_module_with_link_source_is_accepted():
    class _Ok(ChecklistBankModule):
        meta = _meta(can_render_external_link=True)
        dataset_id = "1"
        label = site_name = "X"
        link_source = "usage"
