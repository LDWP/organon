"""Tests de OeppModule : enrichissement seul, exige une correspondance exacte du nom dans les
résultats de recherche (champ "f") avant d'aller chercher la fiche détail."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.oepp.module import OeppModule


class FakeOeppAdapter:
    def __init__(self, search_results: list[dict], detail: dict):
        self._search_results = search_results
        self._detail = detail

    async def search(self, name: str) -> list[dict]:
        return self._search_results

    async def taxon_detail(self, eppo_code: str) -> dict:
        return self._detail


@pytest.mark.asyncio
async def test_collect_adds_link_with_author_and_vernacular():
    module = OeppModule(
        adapter=FakeOeppAdapter(
            search_results=[{"e": "POPTR", "f": "Populus tremula"}],
            detail={"auteur": "L.", "vernaculaire_fr": ["Peuplier tremble"]},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Populus tremula", rank="espèce"), kingdom="vegetal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["oepp"] == {"id": "POPTR", "name": "Populus tremula", "author": "L."}
    assert result.vernacular["OEPP"] == {"fr": ["Peuplier tremble"]}

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{OEPP | POPTR | ''Populus tremula'' | L. | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://gd.eppo.int/taxon/POPTR' target='_blank' "
        "rel='noopener noreferrer'>OEPP</a>"
    )


@pytest.mark.asyncio
async def test_collect_ignores_non_exact_name_matches():
    module = OeppModule(
        adapter=FakeOeppAdapter(
            search_results=[{"e": "POPTR", "f": "Populus tremuloides"}],
            detail={"auteur": None, "vernaculaire_fr": []},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Populus tremula"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    detail = {"auteur": None, "vernaculaire_fr": []}
    module = OeppModule(adapter=FakeOeppAdapter([{"e": "X", "f": "X"}], detail))
    struct = Struct(taxon=TaxonInfo(name="X"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_without_author_or_vernacular():
    module = OeppModule(
        adapter=FakeOeppAdapter(
            search_results=[{"e": "POPTR", "f": "Populus tremula"}],
            detail={"auteur": None, "vernaculaire_fr": []},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Populus tremula"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert "author" not in result.links["oepp"]
    assert "OEPP" not in result.vernacular
