"""Tests de WikimediaModule : orchestrateur agrégeant wikidata/commons/species/wiktionnaire
(toujours) et un lien de portail Wikipédia (enrichissement seul, premier rang famille/ordre/
classe qui en a un — voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, TaxonInfo
from organon.modules.wikimedia.module import WikimediaModule


class FakeWikidataAdapter:
    def __init__(self, qid: str | None):
        self._qid = qid

    async def qid(self, name: str) -> str | None:
        return self._qid


class FakeCommonsAdapter:
    def __init__(self, page: bool = False, category: bool = False):
        self._page = page
        self._category = category

    async def page_exists(self, name: str) -> bool:
        return self._page

    async def category_exists(self, name: str) -> bool:
        return self._category


class FakePageAdapter:
    def __init__(self, exists: bool = False):
        self._exists = exists

    async def page_exists(self, name: str) -> bool:
        return self._exists


class FakeWikipediaAdapter:
    def __init__(
        self,
        portals_by_name: dict[str, list[str]] | None = None,
        categories: set[str] | None = None,
    ):
        self._portals_by_name = portals_by_name or {}
        self._categories = categories or set()
        self.checked_categories: list[str] = []

    async def portails(self, name: str) -> list[str]:
        return self._portals_by_name.get(name, [])

    async def category_exists(self, name: str) -> bool:
        self.checked_categories.append(name)
        return name in self._categories


def _module(**kwargs) -> WikimediaModule:
    defaults = {
        "wikidata": FakeWikidataAdapter(None),
        "commons": FakeCommonsAdapter(),
        "species": FakePageAdapter(),
        "wiktionnaire": FakePageAdapter(),
        "wikipedia": FakeWikipediaAdapter(),
    }
    defaults.update(kwargs)
    return WikimediaModule(**defaults)


@pytest.mark.asyncio
async def test_collect_aggregates_cross_project_links():
    module = _module(
        wikidata=FakeWikidataAdapter("Q140"),
        commons=FakeCommonsAdapter(page=True, category=True),
        species=FakePageAdapter(True),
        wiktionnaire=FakePageAdapter(True),
    )
    struct = Struct(taxon=TaxonInfo(name="Panthera leo"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    data = result.links["wikimedia"]
    assert data["wikidata"] == {"id": "Q140"}
    assert data["commons"] == {"page": "Panthera leo"}
    assert data["commons_category"] == {"page": "Panthera leo"}
    assert data["wikispecies"] == {"page": "Panthera leo"}
    assert data["frwiktionary"] == {"page": "Panthera leo"}
    assert "wikipedia" not in data  # is_classification=True : pas de lookup de portail

    debug = module.debug_link(result)
    assert "wikidata.org/wiki/Q140" in debug
    assert "commons.wikimedia.org/wiki/Panthera_leo" not in debug  # nom non slugifié ici
    assert "commons.wikimedia.org/wiki/Panthera leo" in debug
    assert "Category:Panthera leo" in debug
    assert "species.wikimedia.org/wiki/Panthera leo" in debug
    assert "fr.wiktionary.org/wiki/Panthera leo" in debug


@pytest.mark.asyncio
async def test_collect_enrichment_finds_portal_on_family_rank():
    module = _module(wikipedia=FakeWikipediaAdapter({"Felidae": ["Portail:Mammifères"]}))
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo"),
        ranks=[RankName(name="Felidae", rank="famille"), RankName(name="Carnivora", rank="ordre")],
    )

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    wikipedia = result.links["wikimedia"]["wikipedia"]
    assert wikipedia == {"portals": ["Portail:Mammifères"], "rank": "famille", "name": "Felidae"}

    debug = module.debug_link(result)
    assert "Portail (famille : Felidae)" in debug
    assert "fr.wikipedia.org/wiki/Felidae" in debug


@pytest.mark.asyncio
async def test_collect_returns_none_when_nothing_found():
    module = _module()
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


def test_debug_link_absent_without_data():
    module = _module()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None


@pytest.mark.asyncio
async def test_collect_checks_homonym_categories_up_to_the_first_existing_one():
    wikipedia = FakeWikipediaAdapter(categories={"Chilopoda"})
    module = _module(wikipedia=wikipedia)
    struct = Struct(
        taxon=TaxonInfo(name="Mecistocephalidae", rank="famille"),
        ranks=[
            RankName(name="Geophilomorpha", rank="ordre"),
            RankName(name="Chilopoda", rank="classe"),
            RankName(name="Arthropoda", rank="embranchement"),
        ],
    )

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["wikimedia"]["existing_categories"] == {
        "Mecistocephalidae": False,
        "Geophilomorpha": False,
        "Chilopoda": True,
    }
    assert wikipedia.checked_categories == ["Mecistocephalidae", "Geophilomorpha", "Chilopoda"]


@pytest.mark.asyncio
async def test_collect_checks_no_category_outside_homonym_ranks():
    wikipedia = FakeWikipediaAdapter()
    module = _module(wikipedia=wikipedia)
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo", rank="espèce"),
        ranks=[RankName(name="Felidae", rank="famille")],
    )

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
    assert wikipedia.checked_categories == []
