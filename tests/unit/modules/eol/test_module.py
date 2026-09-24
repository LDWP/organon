"""Tests de EolModule : enrichissement seul, auteur extrait de `scientificName` en retranchant
le nom déjà connu (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.eol.module import EolModule


class FakeEolAdapter:
    def __init__(self, search_results: list[dict], page: dict | None):
        self._search_results = search_results
        self._page = page

    async def search(self, name: str) -> list[dict]:
        return self._search_results

    async def page(self, page_id: int) -> dict | None:
        return self._page


@pytest.mark.asyncio
async def test_collect_extracts_author_from_scientific_name():
    module = EolModule(
        adapter=FakeEolAdapter(
            [{"id": 224626, "title": "Gadus morhua"}],
            {"scientificName": "Gadus morhua Linnaeus, 1758"},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua", rank="espèce"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["eol"] == {
        "id": 224626,
        "name": "Gadus morhua",
        "author": "Linnaeus, 1758",
    }

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{EOL | 224626 | ''Gadus morhua'' Linnaeus, 1758 | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://eol.org/fr/pages/224626' target='_blank' "
        "rel='noopener noreferrer'>EoL</a>"
    )


@pytest.mark.asyncio
async def test_collect_without_page_detail():
    module = EolModule(adapter=FakeEolAdapter([{"id": 1, "title": "Gadus morhua"}], None))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert "author" not in result.links["eol"]


@pytest.mark.asyncio
async def test_collect_ignores_non_exact_title_match():
    module = EolModule(adapter=FakeEolAdapter([{"id": 1, "title": "Gadus morhua morhua"}], None))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = EolModule(adapter=FakeEolAdapter([{"id": 1, "title": "Gadus morhua"}], None))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None
