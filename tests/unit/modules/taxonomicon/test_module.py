"""Tests de TaxonomiconModule : enrichissement seul, ne retient que les correspondances "Valid"
au nom exact (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.taxonomicon.module import TaxonomiconModule


class FakeTaxonomiconAdapter:
    def __init__(self, hits: list[tuple[str, int, str]], author: str | None):
        self._hits = hits
        self._author = author

    async def search(self, name: str) -> list[tuple[str, int, str]]:
        return self._hits

    async def author_citation(self, taxon_id: int) -> str | None:
        return self._author


@pytest.mark.asyncio
async def test_collect_adds_link_with_author():
    module = TaxonomiconModule(
        adapter=FakeTaxonomiconAdapter([("Valid", 12345, "Gadus morhua")], "Linnaeus, 1758")
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua", rank="espèce"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["taxonomicon"] == {
        "id": 12345,
        "name": "Gadus morhua",
        "author": "Linnaeus, 1758",
    }

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{Taxonomicon | 12345 | ''Gadus morhua'' Linnaeus, 1758 | consulté le="
    )
    assert module.debug_link(result) == (
        "<a href='http://taxonomicon.taxonomy.nl/TaxonTree.aspx?id=12345' target='_blank' "
        "rel='noopener noreferrer'>Taxonomicon</a>"
    )


@pytest.mark.asyncio
async def test_collect_ignores_invalid_status():
    module = TaxonomiconModule(
        adapter=FakeTaxonomiconAdapter([("nom. inval.", 1, "Gadus morhua")], None)
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_without_author_citation():
    module = TaxonomiconModule(
        adapter=FakeTaxonomiconAdapter([("Valid", 12345, "Gadus morhua")], None)
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert "author" not in result.links["taxonomicon"]


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = TaxonomiconModule(
        adapter=FakeTaxonomiconAdapter([("Valid", 12345, "Gadus morhua")], None)
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None
