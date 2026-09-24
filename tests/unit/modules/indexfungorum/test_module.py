"""Tests de IndexFungorumModule : classification fongique, chaîne fixe genre->embranchement
(NameByKey ne la joint que pour les enregistrements de rang genre et en dessous), suivi du nom
accepté via CURRENT_NAME_RECORD_NUMBER (voir module.py)."""

from __future__ import annotations

import asyncio
import time

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.indexfungorum.module import IndexFungorumModule

AMANITA_MUSCARIA_FULL = {
    "RECORD_NUMBER": 123,
    "CURRENT_NAME_RECORD_NUMBER": 123,
    "NAME_OF_FUNGUS": "Amanita muscaria",
    "AUTHORS": "(L.) Lam.",
    "YEAR_OF_PUBLICATION": "1783",
    "INFRASPECIFIC_RANK": "sp.",
    "Genus_name": "Amanita",
    "Family_name": "Amanitaceae",
    "Order_name": "Agaricales",
    "Subclass_name": "Incertae sedis",
    "Class_name": "Agaricomycetes",
    "Subphylum_name": "Agaricomycotina",
    "Phylum_name": "Basidiomycota",
    "Kingdom_name": "Fungi",
}


class FakeIndexFungorumAdapter:
    def __init__(
        self,
        search_hits: list[dict],
        by_key: dict[int, dict] | None = None,
        synonyms: list[dict] | None = None,
    ):
        self._search_hits = search_hits
        self._by_key = by_key or {}
        self._synonyms = synonyms or []

    async def name_search(self, name: str, max_number: int = 50) -> list[dict]:
        return self._search_hits

    async def name_by_key(self, record_number: int) -> dict | None:
        return self._by_key.get(record_number)

    async def names_by_current_key(self, record_number: int) -> list[dict]:
        return self._synonyms


def _hit(record):
    return {
        "NAME_OF_FUNGUS": record["NAME_OF_FUNGUS"],
        "RECORD_NUMBER": record["RECORD_NUMBER"],
        "CURRENT_NAME_RECORD_NUMBER": record["CURRENT_NAME_RECORD_NUMBER"],
    }


@pytest.mark.asyncio
async def test_collect_classification_species_with_ladder_and_synonyms():
    module = IndexFungorumModule(
        adapter=FakeIndexFungorumAdapter(
            [_hit(AMANITA_MUSCARIA_FULL)],
            {123: AMANITA_MUSCARIA_FULL},
            synonyms=[
                {"RECORD_NUMBER": 456, "NAME_OF_FUNGUS": "Agaricus muscarius", "AUTHORS": "L."},
                {
                    "RECORD_NUMBER": 123,
                    "NAME_OF_FUNGUS": "Amanita muscaria",
                    "AUTHORS": "(L.) Lam.",
                },
            ],
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Amanita muscaria"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "speciesfungorum"
    assert result.kingdom == "champignon"
    assert result.taxon.author == "(L.) Lam., 1783"
    assert [r.name for r in result.ranks] == [
        "Amanita",
        "Amanitaceae",
        "Agaricales",
        "Agaricomycetes",
        "Agaricomycotina",
        "Basidiomycota",
    ]
    assert result.synonyms.items[0].name == "Agaricus muscarius"
    assert len(result.synonyms.items) == 1  # l'enregistrement lui-même est exclu

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{Fungorum espèce | 123 | Amanita muscaria | (L.) Lam., 1783")
    assert module.debug_link(result) == (
        "<a href='http://www.indexfungorum.org/names/NamesRecord.asp?RecordID=123' "
        "target='_blank' rel='noopener noreferrer'>Index Fungorum</a>"
    )


@pytest.mark.asyncio
async def test_collect_redirects_synonym_when_classifying():
    synonym_hit = {
        "NAME_OF_FUNGUS": "Agaricus muscarius",
        "RECORD_NUMBER": 456,
        "CURRENT_NAME_RECORD_NUMBER": 123,
    }
    synonym_full = {**synonym_hit, "AUTHORS": "L."}
    module = IndexFungorumModule(
        adapter=FakeIndexFungorumAdapter(
            [synonym_hit], {456: synonym_full, 123: AMANITA_MUSCARIA_FULL}
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Agaricus muscarius"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Amanita muscaria"
    assert result.links["indexfungorum"]["synonym"] is True
    assert result.classification == "speciesfungorum"


@pytest.mark.asyncio
async def test_collect_enrichment_flags_synonym_without_redirect():
    synonym_hit = {
        "NAME_OF_FUNGUS": "Agaricus muscarius",
        "RECORD_NUMBER": 456,
        "CURRENT_NAME_RECORD_NUMBER": 123,
    }
    synonym_full = {**synonym_hit, "AUTHORS": "L."}
    module = IndexFungorumModule(
        adapter=FakeIndexFungorumAdapter(
            [synonym_hit], {456: synonym_full, 123: AMANITA_MUSCARIA_FULL}
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Agaricus muscarius"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["indexfungorum"]["synonym"] is True


@pytest.mark.asyncio
async def test_collect_family_rank_insufficient_for_classification():
    family_record = {
        "RECORD_NUMBER": 999,
        "CURRENT_NAME_RECORD_NUMBER": 999,
        "NAME_OF_FUNGUS": "Amanitaceae",
        "AUTHORS": "R. Heim ex Pouzar",
        "INFRASPECIFIC_RANK": "fam.",
        # Pas de Genus_name : NameByKey ne joint la hiérarchie qu'au rang genre et en dessous.
    }
    module = IndexFungorumModule(
        adapter=FakeIndexFungorumAdapter([_hit(family_record)], {999: family_record})
    )
    struct = Struct(taxon=TaxonInfo(name="Amanitaceae"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = IndexFungorumModule(adapter=FakeIndexFungorumAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_gathers_basionym_and_synonyms():
    """`name_by_key(basionym_id)` et `names_by_current_key` ne dépendent que de `full`, jamais
    l'un de l'autre (voir module.py) : le résultat doit rester correct qu'ils soient appelés
    en série ou en parallèle via asyncio.gather."""
    full_with_basionym = {**AMANITA_MUSCARIA_FULL, "BASIONYM_RECORD_NUMBER": 789}
    basionym_record = {
        "RECORD_NUMBER": 789,
        "NAME_OF_FUNGUS": "Agaricus muscarius",
        "AUTHORS": "L.",
    }
    module = IndexFungorumModule(
        adapter=FakeIndexFungorumAdapter(
            [_hit(full_with_basionym)],
            {123: full_with_basionym, 789: basionym_record},
            synonyms=[
                {"RECORD_NUMBER": 456, "NAME_OF_FUNGUS": "Agaricus muscarius var. alba", "AUTHORS": "L."},
            ],
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Amanita muscaria"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.basionym.name == "Agaricus muscarius"
    assert result.basionym.author == "L."
    assert result.basionym.source == "Index Fungorum"
    assert result.synonyms.items[0].name == "Agaricus muscarius var. alba"


class DelayedIndexFungorumAdapter(FakeIndexFungorumAdapter):
    """Ajoute un délai artificiel à `name_by_key`/`names_by_current_key` pour prouver que les
    deux appels tournent en parallèle (asyncio.gather) plutôt qu'en série."""

    DELAY = 0.1

    async def name_by_key(self, record_number: int) -> dict | None:
        await asyncio.sleep(self.DELAY)
        return await super().name_by_key(record_number)

    async def names_by_current_key(self, record_number: int) -> list[dict]:
        await asyncio.sleep(self.DELAY)
        return await super().names_by_current_key(record_number)


@pytest.mark.asyncio
async def test_collect_basionym_and_synonyms_run_concurrently():
    full_with_basionym = {**AMANITA_MUSCARIA_FULL, "BASIONYM_RECORD_NUMBER": 789}
    basionym_record = {
        "RECORD_NUMBER": 789,
        "NAME_OF_FUNGUS": "Agaricus muscarius",
        "AUTHORS": "L.",
    }
    module = IndexFungorumModule(
        adapter=DelayedIndexFungorumAdapter(
            [_hit(full_with_basionym)], {123: full_with_basionym, 789: basionym_record}
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Amanita muscaria"))

    start = time.monotonic()
    result = await module.collect(struct, is_classification=True, options=GenerateOptions())
    elapsed = time.monotonic() - start

    assert result is not None
    # En série : name_by_key(accepted) + name_by_key(basionyme) + names_by_current_key
    # = 3 x DELAY. En parallèle (gather sur les deux derniers) : 2 x DELAY. Seuil à 2.5x pour
    # laisser de la marge au timing sans masquer une régression vers l'exécution série.
    assert elapsed < DelayedIndexFungorumAdapter.DELAY * 2.5
