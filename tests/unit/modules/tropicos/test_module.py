"""Tests de TropicosModule : enrichissement botanique pur, ne retient que les résultats dont
`fullName` correspond exactement au nom recherché (voir module.py pour la limite assumée sur les
homonymes exacts)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.tropicos.module import TropicosModule


class FakeTropicosAdapter:
    def __init__(self, results: list[dict]):
        self._results = results

    async def search(self, name: str) -> list[dict]:
        return self._results


@pytest.mark.asyncio
async def test_collect_adds_link_from_exact_match():
    module = TropicosModule(
        adapter=FakeTropicosAdapter(
            [{"id": 2700275, "fullName": "Quercus robur", "authorString": "L."}]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tropicos"] == {"id": 2700275, "name": "Quercus robur", "author": "L."}

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{Tropicos | 2700275 | Quercus robur | L. | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://tropicos.org/name/2700275' target='_blank' "
        "rel='noopener noreferrer'>Tropicos</a>"
    )


@pytest.mark.asyncio
async def test_collect_ignores_non_exact_homonyms():
    module = TropicosModule(
        adapter=FakeTropicosAdapter(
            [{"id": 1, "fullName": "Quercus robur var. pendula", "authorString": "Loudon"}]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_picks_first_of_several_exact_homonyms():
    module = TropicosModule(
        adapter=FakeTropicosAdapter(
            [
                {"id": 1, "fullName": "Quercus robur", "authorString": "(Ten.) A. DC."},
                {"id": 2, "fullName": "Quercus robur", "authorString": "L."},
            ]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tropicos"]["id"] == 1


@pytest.mark.asyncio
async def test_collect_prefers_accepted_name_marked_by_bang():
    module = TropicosModule(
        adapter=FakeTropicosAdapter(
            [
                {
                    "id": 50280607,
                    "fullName": "Quercus robur",
                    "authorString": "(Ten.) A. DC.",
                    "displayName": "Quercus robur (Ten.) A. DC.",
                },
                {
                    "id": 13100004,
                    "fullName": "Quercus robur",
                    "authorString": "L.",
                    "displayName": "! Quercus robur L.",
                },
            ]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tropicos"] == {"id": 13100004, "name": "Quercus robur", "author": "L."}


@pytest.mark.asyncio
async def test_collect_accepts_double_bang_and_ignores_synonym_stars():
    module = TropicosModule(
        adapter=FakeTropicosAdapter(
            [
                {"id": 1, "fullName": "Poaceae", "displayName": "* Poaceae Rchb."},
                {"id": 2, "fullName": "Poaceae", "displayName": "!! Poaceae Barnhart"},
            ]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Poaceae"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tropicos"]["id"] == 2


@pytest.mark.asyncio
async def test_collect_not_found():
    module = TropicosModule(adapter=FakeTropicosAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent():
    module = TropicosModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None
