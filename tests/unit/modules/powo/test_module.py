"""Tests de PowoModule : classification botanique (WCVP), distribution géographique (dict de
catégories TDWG, pas une liste de codes brute — voir docstring de module.py pour le bug
historique corrigé), rangs supra-familiaux en champs scalaires séparés de la chaîne."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.powo.module import PowoModule

QUERCUS_ROBUR_ID = "urn:lsid:ipni.org:names:242415-1"

QUERCUS_ROBUR_DETAIL = {
    "name": "Quercus robur",
    "authors": "L.",
    "namePublishedInYear": "1753",
    "rank": "SPECIES",
    "taxonomicStatus": "Accepted",
    "kingdom": "Plantae",
    "classification": [
        {"fqId": "urn:lsid:ipni.org:names:30000067-2", "name": "Fagaceae", "rank": "FAMILY"},
        {"fqId": "urn:lsid:ipni.org:names:326199-2", "name": "Quercus", "rank": "GENUS"},
        {"fqId": QUERCUS_ROBUR_ID, "name": "Quercus robur", "rank": "SPECIES"},
    ],
    "order": "Fagales",
    "distribution": {
        "natives": [{"tdwgCode": "FRA", "establishment": "Native"}],
        "introduced": [{"tdwgCode": "USA", "establishment": "Introduced"}],
    },
    "synonyms": [{"name": "Quercus pedunculata", "author": "Ehrh.", "rank": "SPECIES"}],
    "childNameUsages": [
        {
            "name": "Quercus robur subsp. robur",
            "author": "L.",
            "rank": "SUBSPECIES",
            "taxonomicStatus": "Accepted",
        }
    ],
}


class FakePowoAdapter:
    def __init__(self, search_hits: list[dict], detail_by_id: dict[str, dict] | None = None):
        self._by_name: dict[str, list[dict]] = {}
        for hit in search_hits:
            self._by_name.setdefault(hit["name"], []).append(hit)
        self._detail_by_id = detail_by_id or {}

    async def search(self, name: str) -> list[dict]:
        return self._by_name.get(name, [])

    async def lookup(self, fq_id: str, include: list[str] | None = None) -> dict | None:
        return self._detail_by_id.get(fq_id)


@pytest.mark.asyncio
async def test_collect_classification_full():
    module = PowoModule(
        adapter=FakePowoAdapter(
            [{"name": "Quercus robur", "accepted": True, "fqId": QUERCUS_ROBUR_ID}],
            {QUERCUS_ROBUR_ID: QUERCUS_ROBUR_DETAIL},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "POWO"
    assert result.kingdom == "végétal"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "L., 1753"
    assert result.links["powo"]["id"] == "242415-1"
    assert [r.name for r in result.ranks] == ["Quercus", "Fagaceae", "Fagales"]

    dist = result.distribution["powo"]
    assert dist.certain == {"FRA": "FRA", "USA": "USA"}
    assert dist.introduced == {"USA": "USA"}
    assert dist.uncertain == {}

    assert result.synonyms.items[0].name == "Quercus pedunculata"
    assert result.subtaxa.items[0].name == "Quercus robur subsp. robur"

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{POWO | 242415-1 | Quercus robur | L., 1753 | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:242415-1' "
        "target='_blank' rel='noopener noreferrer'>POWO</a>"
    )


@pytest.mark.asyncio
async def test_collect_synonym_redirects_to_accepted_when_classifying():
    synonym_id = "urn:lsid:ipni.org:names:242416-1"
    synonym_detail = {
        **QUERCUS_ROBUR_DETAIL,
        "name": "Quercus pedunculata",
        "taxonomicStatus": "Synonym",
        "accepted": {"fqId": QUERCUS_ROBUR_ID, "name": "Quercus robur"},
    }
    module = PowoModule(
        adapter=FakePowoAdapter(
            [
                {"name": "Quercus pedunculata", "accepted": False, "fqId": synonym_id},
                {"name": "Quercus robur", "accepted": True, "fqId": QUERCUS_ROBUR_ID},
            ],
            {synonym_id: synonym_detail, QUERCUS_ROBUR_ID: QUERCUS_ROBUR_DETAIL},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus pedunculata"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Quercus robur"
    assert result.classification == "POWO"


@pytest.mark.asyncio
async def test_collect_synonym_enrichment_flags_without_redirect():
    synonym_id = "urn:lsid:ipni.org:names:242416-1"
    synonym_detail = {
        **QUERCUS_ROBUR_DETAIL,
        "name": "Quercus pedunculata",
        "taxonomicStatus": "Synonym",
        "accepted": {"fqId": QUERCUS_ROBUR_ID, "name": "Quercus robur"},
    }
    module = PowoModule(
        adapter=FakePowoAdapter(
            [{"name": "Quercus pedunculata", "accepted": False, "fqId": synonym_id}],
            {synonym_id: synonym_detail},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus pedunculata"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["powo"]["synonym"] is True
    bioref = module.render_bioref(result)
    assert " | nv" in bioref


@pytest.mark.asyncio
async def test_collect_distribution_falls_back_to_flat_locations():
    detail = {**QUERCUS_ROBUR_DETAIL, "distribution": None, "locations": ["FRA", "DEU"]}
    module = PowoModule(
        adapter=FakePowoAdapter(
            [{"name": "Quercus robur", "accepted": True, "fqId": QUERCUS_ROBUR_ID}],
            {QUERCUS_ROBUR_ID: detail},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.distribution["powo"].certain == {"FRA": "FRA", "DEU": "DEU"}


@pytest.mark.asyncio
async def test_collect_ignores_non_exact_name_match():
    module = PowoModule(
        adapter=FakePowoAdapter(
            [{"name": "Quercus robur subsp. robur", "accepted": True, "fqId": "x"}]
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = PowoModule(adapter=FakePowoAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
