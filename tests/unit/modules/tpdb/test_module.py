"""Tests de TpdbModule : enrichissement seul, id résolu par recherche puis rang/auteur/statut nv
par un second appel `taxa/single.json` (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.tpdb.module import TpdbModule


class FakeTpdbAdapter:
    def __init__(self, search_results: list[dict], detail: dict | None):
        self._search_results = search_results
        self._detail = detail

    async def search(self, name: str) -> list[dict]:
        return self._search_results

    async def taxon_by_name(self, name: str) -> dict | None:
        return self._detail


@pytest.mark.asyncio
async def test_collect_adds_link_with_rank_and_author():
    module = TpdbModule(
        adapter=FakeTpdbAdapter(
            [{"record_id": "txn:54980", "name": "Tyrannosaurus rex"}],
            {
                "taxon_name": "Tyrannosaurus rex",
                "taxon_rank": "species",
                "taxon_attr": "Osborn, 1905",
            },
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Tyrannosaurus rex"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tpdb"] == {
        "id": "txn:54980",
        "name": "Tyrannosaurus rex",
        "rank": "espèce",
        "author": "Osborn, 1905",
    }

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{TPDB | txn:54980 | ''Tyrannosaurus rex'' Osborn, 1905 | consulté le="
    )
    assert module.debug_link(result) == (
        "<a href='https://paleobiodb.org/classic/basicTaxonInfo?taxon_no=txn:54980' "
        "target='_blank' rel='noopener noreferrer'>TPDB</a>"
    )


@pytest.mark.asyncio
async def test_collect_flags_non_valid_status_when_accepted_name_differs():
    module = TpdbModule(
        adapter=FakeTpdbAdapter(
            [{"record_id": "txn:1", "name": "Brontosaurus excelsus"}],
            {
                "taxon_name": "Brontosaurus excelsus",
                "accepted_name": "Apatosaurus excelsus",
                "taxon_rank": "species",
            },
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Brontosaurus excelsus"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tpdb"]["invalid"] is True


@pytest.mark.asyncio
async def test_collect_last_exact_name_match_wins():
    module = TpdbModule(
        adapter=FakeTpdbAdapter(
            [
                {"record_id": "txn:1", "name": "Gadus morhua"},
                {"record_id": "txn:2", "name": "Gadus morhua"},
            ],
            None,
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["tpdb"]["id"] == "txn:2"


@pytest.mark.asyncio
async def test_collect_not_found():
    module = TpdbModule(adapter=FakeTpdbAdapter([], None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = TpdbModule(
        adapter=FakeTpdbAdapter([{"record_id": "txn:1", "name": "X"}], None)
    )
    struct = Struct(taxon=TaxonInfo(name="X"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None
