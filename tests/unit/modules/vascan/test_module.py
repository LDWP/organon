"""Tests de VascanModule : enrichissement botanique régional (flore du Canada), marque le
statut synonyme sans suivre la cible acceptée (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.vascan.module import VascanModule


class FakeVascanAdapter:
    def __init__(self, matches: list[dict]):
        self._matches = matches

    async def search(self, name: str) -> list[dict]:
        return self._matches


ACER_RUBRUM = {
    "taxonID": "1587",
    "canonicalName": "Acer rubrum",
    "scientificNameAuthorship": "L.",
    "taxonomicAssertions": [{"taxonomicStatus": "accepted"}],
    "vernacularNames": [
        {"language": "fr", "vernacularName": "Érable rouge"},
        {"language": "en", "vernacularName": "Red maple"},
    ],
}


@pytest.mark.asyncio
async def test_collect_adds_link_and_french_vernacular():
    module = VascanModule(adapter=FakeVascanAdapter([ACER_RUBRUM]))
    struct = Struct(taxon=TaxonInfo(name="Acer rubrum"), kingdom="végétal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["vascan"] == {"id": "1587", "name": "Acer rubrum", "author": "L."}
    assert result.vernacular["VASCAN"] == {"fr": ["Érable rouge"], "en": ["Red maple"]}

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{VASCAN | 1587 | ''Acer rubrum'' L. | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://data.canadensys.net/vascan/taxon/1587' target='_blank' "
        "rel='noopener noreferrer'>VASCAN</a>"
    )


@pytest.mark.asyncio
async def test_collect_flags_synonym_status():
    match = {**ACER_RUBRUM, "taxonomicAssertions": [{"taxonomicStatus": "synonym"}]}
    module = VascanModule(adapter=FakeVascanAdapter([match]))
    struct = Struct(taxon=TaxonInfo(name="Acer rubrum"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["vascan"]["synonym"] is True
    bioref = module.render_bioref(result)
    assert " | nv" in bioref
    assert bioref.rstrip().endswith("}}")


@pytest.mark.asyncio
async def test_collect_deduplicates_repeated_french_names():
    match = {
        **ACER_RUBRUM,
        "vernacularNames": [
            {"language": "fr", "vernacularName": "Érable rouge"},
            {"language": "fr", "vernacularName": "Érable rouge"},
        ],
    }
    module = VascanModule(adapter=FakeVascanAdapter([match]))
    struct = Struct(taxon=TaxonInfo(name="Acer rubrum"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.vernacular["VASCAN"] == {"fr": ["Érable rouge"]}


@pytest.mark.asyncio
async def test_collect_not_found():
    module = VascanModule(adapter=FakeVascanAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_rejects_match_with_different_name():
    # La recherche VASCAN est floue : « Chaetodon » renvoie un épithète homonyme d'une plante.
    match = {
        "taxonID": "27096",
        "canonicalName": "Astragalus chaetodon",
        "scientificNameAuthorship": "Torrey ex A. Gray nom. illeg.",
        "taxonomicAssertions": [{"taxonomicStatus": "synonym"}],
    }
    module = VascanModule(adapter=FakeVascanAdapter([match]))
    struct = Struct(taxon=TaxonInfo(name="Chaetodon", rank="genre"), kingdom="végétal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_picks_exact_name_among_matches():
    other = {**ACER_RUBRUM, "taxonID": "9", "canonicalName": "Acer rubrum var. drummondii"}
    module = VascanModule(adapter=FakeVascanAdapter([other, ACER_RUBRUM]))
    struct = Struct(taxon=TaxonInfo(name="Acer rubrum"), kingdom="végétal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result.links["vascan"]["id"] == "1587"


@pytest.mark.asyncio
async def test_collect_skips_non_plant_kingdom():
    module = VascanModule(adapter=FakeVascanAdapter([ACER_RUBRUM]))
    struct = Struct(taxon=TaxonInfo(name="Acer rubrum"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
