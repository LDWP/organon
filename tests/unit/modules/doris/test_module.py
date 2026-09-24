"""Tests de DorisModule : enrichissement seul (le site ne fournit aucune donnée de
classification exploitable, voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.doris.module import DorisModule


class FakeDorisAdapter:
    def __init__(self, hit: tuple[str, str | None] | None):
        self._hit = hit

    async def search(self, name: str) -> tuple[str, str | None] | None:
        return self._hit


@pytest.mark.asyncio
async def test_collect_adds_link():
    module = DorisModule(adapter=FakeDorisAdapter(("1234", "Poulpe commun")))
    struct = Struct(
        taxon=TaxonInfo(name="Octopus vulgaris", rank="espèce", resolved_author="Cuvier, 1797")
    )

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["doris"] == {
        "id": "1234",
        "name": "Octopus vulgaris",
        "common_name": "Poulpe commun",
    }

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{DORIS | 1234 | ''Octopus vulgaris'' Cuvier, 1797 | consulté le="
    )
    assert module.debug_link(result) == (
        "<a href='https://doris.ffessm.fr/fiche2.asp?fiche_numero=1234' target='_blank' "
        "rel='noopener noreferrer'>DORIS</a>"
    )


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = DorisModule(adapter=FakeDorisAdapter(("1234", None)))
    struct = Struct(taxon=TaxonInfo(name="X"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = DorisModule(adapter=FakeDorisAdapter(None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent():
    module = DorisModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None
