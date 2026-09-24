"""Tests de EfloraModule : une fiche possible par flore régionale, ne retient que les résultats
dont le nom correspond exactement au taxon demandé (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.eflora.module import EfloraModule


class FakeEfloraAdapter:
    def __init__(self, hits: list[tuple[str, str, str]]):
        self._hits = hits

    async def search(self, name: str) -> list[tuple[str, str, str]]:
        return self._hits


@pytest.mark.asyncio
async def test_collect_adds_one_link_per_flora():
    module = EfloraModule(
        adapter=FakeEfloraAdapter(
            [
                ("1", "242415071", "Quercus robur"),
                ("2", "200006198", "Quercus robur"),
                ("2", "200006199", "Quercus petraea"),  # nom différent, exclu
            ]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["eflora"]["ids"] == [("1", "242415071"), ("2", "200006198")]

    bioref = module.render_bioref(result)
    assert len(bioref) == 2
    assert bioref[0].startswith("{{EFloras | 1 | 242415071 | Quercus robur | consulté le=")
    assert bioref[1].startswith("{{EFloras | 2 | 200006198 | Quercus robur | consulté le=")

    debug = module.debug_link(result)
    assert "eFlora (1)" in debug
    assert "eFlora (2)" in debug
    assert "flora_id=1&taxon_id=242415071" in debug


@pytest.mark.asyncio
async def test_collect_returns_none_without_exact_match():
    module = EfloraModule(adapter=FakeEfloraAdapter([("1", "1", "Quercus petraea")]))
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = EfloraModule(adapter=FakeEfloraAdapter([("1", "1", "Quercus robur")]))
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent():
    module = EfloraModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None
