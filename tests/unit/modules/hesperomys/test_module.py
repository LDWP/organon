"""Tests de HesperomysModule : classification mammalienne uniquement (`class_.validName ==
"Mammalia"`, sinon abandon), pas de suivi de synonyme, citation combinant auteur(s)+année
extraite de `baseName` (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.hesperomys.module import HesperomysModule

_FISCHER_BASE_NAME = {
    "authorTags": [{"__typename": "Author", "person": {"familyName": "Fischer"}}],
    "year": "1780-01-01",
}

_PEROMYSCUS_DETAIL = {
    "oid": 42,
    "validName": "Peromyscus leucopus",
    "rank": "species",
    "age": "extant",
    "baseName": _FISCHER_BASE_NAME,
    "class_": {"validName": "Mammalia"},
    "parent": {"oid": 41, "rank": "genus", "validName": "Peromyscus"},
    "names": {
        "edges": [
            {
                "node": {
                    "status": "valid",
                    "correctedOriginalName": "Peromyscus leucopus",
                }
            },
            {
                "node": {
                    "status": "synonym",
                    "correctedOriginalName": "Mus leucopus",
                    "originalRank": "species",
                    "authorTags": _FISCHER_BASE_NAME["authorTags"],
                    "year": "1780-01-01",
                }
            },
        ]
    },
}

_ANCESTORS = [
    {"oid": 41, "rank": "genus", "validName": "Peromyscus", "baseName": None},
    {"oid": 40, "rank": "family", "validName": "Cricetidae", "baseName": None},
]


class FakeHesperomysAdapter:
    def __init__(
        self, results: list[dict], detail: dict | None, ancestors: list[dict] | None = None
    ):
        self._results = results
        self._detail = detail
        self._ancestors = ancestors or []

    async def taxon_by_label(self, label: str) -> list[dict]:
        return self._results

    async def taxon_detail(self, oid: int) -> dict | None:
        return self._detail

    async def ancestors(self, first_parent: dict | None) -> list[dict]:
        return self._ancestors


@pytest.mark.asyncio
async def test_collect_classification_mammal_species():
    module = HesperomysModule(
        adapter=FakeHesperomysAdapter(
            [{"validName": "Peromyscus leucopus", "oid": 42}], _PEROMYSCUS_DETAIL, _ANCESTORS
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Peromyscus leucopus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "Hesperomys"
    assert result.kingdom == "animal"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Fischer, 1780"
    assert result.links["hesperomys"]["id"] == 42
    assert [r.name for r in result.ranks] == ["Peromyscus", "Cricetidae"]

    assert result.synonyms is not None
    assert result.synonyms.items[0].name == "Mus leucopus"
    assert result.synonyms.items[0].author == "Fischer, 1780"

    assert module.debug_link(result) == (
        "<a href='https://hesperomys.com/t/42' target='_blank' "
        "rel='noopener noreferrer'>Hesperomys</a>"
    )


@pytest.mark.asyncio
async def test_collect_classification_rejects_non_mammal():
    detail = {**_PEROMYSCUS_DETAIL, "class_": {"validName": "Aves"}}
    module = HesperomysModule(
        adapter=FakeHesperomysAdapter([{"validName": "Peromyscus leucopus", "oid": 42}], detail)
    )
    struct = Struct(taxon=TaxonInfo(name="Peromyscus leucopus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_enrichment_only_does_not_require_mammal_class():
    detail = {**_PEROMYSCUS_DETAIL, "class_": {"validName": "Aves"}}
    module = HesperomysModule(
        adapter=FakeHesperomysAdapter([{"validName": "Peromyscus leucopus", "oid": 42}], detail)
    )
    struct = Struct(taxon=TaxonInfo(name="Peromyscus leucopus"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["hesperomys"]["id"] == 42
    assert result.classification == ""


@pytest.mark.asyncio
async def test_collect_rejects_removed_or_redirected_taxa():
    detail = {**_PEROMYSCUS_DETAIL, "age": "removed"}
    module = HesperomysModule(
        adapter=FakeHesperomysAdapter([{"validName": "Peromyscus leucopus", "oid": 42}], detail)
    )
    struct = Struct(taxon=TaxonInfo(name="Peromyscus leucopus"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = HesperomysModule(adapter=FakeHesperomysAdapter([], None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
