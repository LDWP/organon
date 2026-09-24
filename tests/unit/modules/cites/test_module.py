"""Tests de CitesModule : enrichissement seul, exige une correspondance exacte de nom (autocomplete)
avant d'aller chercher la fiche détaillée et sa première annexe CITES."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.cites.module import CitesModule


class FakeCitesAdapter:
    def __init__(self, candidates: list[dict], detail: dict | None):
        self._candidates = candidates
        self._detail = detail

    async def autocomplete(self, name: str) -> list[dict]:
        return self._candidates

    async def taxon_concept(self, taxon_id: int) -> dict | None:
        return self._detail


PANTHERA_LEO_DETAIL = {
    "full_name": "Panthera leo",
    "author_year": "(Linnaeus, 1758)",
    "cites_listings": [{"species_listing_name": "II", "effective_at_formatted": "1977-02-04"}],
    "common_names": [
        {"lang": "French", "names": "Lion, Lion d'Afrique"},
        {"lang": "English", "names": "Lion"},
    ],
}


@pytest.mark.asyncio
async def test_collect_adds_link_and_french_vernacular():
    module = CitesModule(
        adapter=FakeCitesAdapter(
            [{"id": 42, "full_name": "Panthera leo"}], PANTHERA_LEO_DETAIL
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Panthera leo", rank="espèce"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["cites"] == {
        "id": 42,
        "name": "Panthera leo",
        "author": "(Linnaeus, 1758)",
        "appendix": "II",
        "date": "1977-02-04",
    }
    assert result.vernacular["CITES espèce"] == {
        "fr": ["Lion", "Lion d'Afrique"],
        "en": ["Lion"],
    }

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{CITES species+ | 42 | ''Panthera leo'' | (Linnaeus, 1758) | consulté le="
    )
    assert module.debug_link(result) == (
        "<a href='https://www.speciesplus.net/#/taxon_concepts/42/legal' target='_blank' "
        "rel='noopener noreferrer'>CITES species+</a>"
    )


@pytest.mark.asyncio
async def test_collect_ignores_null_names_field():
    detail = {**PANTHERA_LEO_DETAIL, "common_names": [{"lang": "French", "names": None}]}
    candidates = [{"id": 42, "full_name": "Panthera leo"}]
    module = CitesModule(adapter=FakeCitesAdapter(candidates, detail))
    struct = Struct(taxon=TaxonInfo(name="Panthera leo"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert "CITES espèce" not in result.vernacular


@pytest.mark.asyncio
async def test_collect_ignores_non_exact_name_match():
    module = CitesModule(
        adapter=FakeCitesAdapter([{"id": 1, "full_name": "Panthera leo persica"}], None)
    )
    struct = Struct(taxon=TaxonInfo(name="Panthera leo"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_returns_none_without_cites_listing():
    detail = {**PANTHERA_LEO_DETAIL, "cites_listings": []}
    candidates = [{"id": 42, "full_name": "Panthera leo"}]
    module = CitesModule(adapter=FakeCitesAdapter(candidates, detail))
    struct = Struct(taxon=TaxonInfo(name="Panthera leo"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = CitesModule(
        adapter=FakeCitesAdapter([{"id": 42, "full_name": "Panthera leo"}], PANTHERA_LEO_DETAIL)
    )
    struct = Struct(taxon=TaxonInfo(name="Panthera leo"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent():
    module = CitesModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None
