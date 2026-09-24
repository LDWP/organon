"""Tests de LpsnModule : classification bactérienne/archée via remontée manuelle de
`lpsn_parent_id` jusqu'au domaine (pas de route API équivalente à AphiaClassificationByAphiaID,
voir module.py), suivi de synonyme par `lpsn_correct_name_id`."""

from __future__ import annotations

import asyncio

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.lpsn.module import LpsnModule

ESCHERICHIA_COLI = {
    "id": 776,
    "full_name": "Escherichia coli",
    "category": "species",
    "monomial": "Escherichia",
    "species_epithet": "coli",
    "authority": "(Migula 1895) Castellani and Chalmers 1919",
    "lpsn_parent_id": 700,
    "lpsn_correct_name_id": 776,
    "publication_text": "Migula, W. 1895. Bacteriaceae.",
}
ESCHERICHIA_GENUS = {
    "id": 700,
    "full_name": "Escherichia",
    "category": "genus",
    "lpsn_parent_id": 650,
}
ENTEROBACTERIACEAE = {
    "id": 650,
    "full_name": "Enterobacteriaceae",
    "category": "family",
    "lpsn_parent_id": 600,
}
BACTERIA_DOMAIN = {"id": 600, "full_name": "Bacteria", "category": "domain"}

RECORDS_BY_ID = {
    776: ESCHERICHIA_COLI,
    700: ESCHERICHIA_GENUS,
    650: ENTEROBACTERIACEAE,
    600: BACTERIA_DOMAIN,
}


class FakeLpsnAdapter:
    def __init__(
        self,
        search_ids: list[int],
        records_by_id: dict[int, dict] | None = None,
        children_ids: list[int] | None = None,
    ):
        self._search_ids = search_ids
        self._records_by_id = records_by_id or {}
        self._children_ids = children_ids or []

    async def advanced_search(self, taxon_name: str) -> list[int]:
        return self._search_ids

    async def fetch(self, ids: list[int]) -> list[dict]:
        return [self._records_by_id[i] for i in ids if i in self._records_by_id]

    async def fetch_one(self, record_id: int) -> dict | None:
        return self._records_by_id.get(record_id)

    async def flexible_search(self, filters: dict) -> list[int]:
        return self._children_ids


class ConcurrencyTrackingLpsnAdapter(FakeLpsnAdapter):
    """Retarde artificiellement `fetch_one`/`flexible_search` pour observer si plusieurs appels
    sont réellement en vol en même temps (`asyncio.gather`) plutôt qu'enchaînés un par un."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.max_concurrent = 0
        self._in_flight = 0

    async def _track(self) -> None:
        self._in_flight += 1
        self.max_concurrent = max(self.max_concurrent, self._in_flight)
        await asyncio.sleep(0.01)
        self._in_flight -= 1

    async def fetch_one(self, record_id: int) -> dict | None:
        await self._track()
        return await super().fetch_one(record_id)

    async def flexible_search(self, filters: dict) -> list[int]:
        await self._track()
        return await super().flexible_search(filters)


BASIONYM_RECORD = {"id": 500, "full_name": "Bacterium coli", "authority": "Migula 1895"}
TYPE_RECORD = {
    "id": 501,
    "full_name": "Escherichia coli ATCC 11775",
    "category": "subspecies",
    "authority": "Castellani and Chalmers 1919",
}
CHILD_RECORD = {
    "id": 900,
    "full_name": "Escherichia coli subsp. foo",
    "category": "subspecies",
    "authority": "Bar 2000",
    "lpsn_correct_name_id": None,
}


@pytest.mark.asyncio
async def test_collect_classification_populates_basionym_type_and_children_concurrently():
    """Régression : basionyme, type nomenclatural et sous-taxons sont trois blocs réseau
    indépendants de `_process` (aucun ne consomme le résultat d'un autre), parallélisables sans
    changer le résultat. `max_concurrent` prouve qu'ils tournent bien en même temps."""
    record = {**ESCHERICHIA_COLI, "basonym_id": 500, "nomenclatural_type_id": 501}
    records = {
        **RECORDS_BY_ID,
        776: record,
        500: BASIONYM_RECORD,
        501: TYPE_RECORD,
        900: CHILD_RECORD,
    }
    adapter = ConcurrencyTrackingLpsnAdapter([776], records, children_ids=[900])
    module = LpsnModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name="Escherichia coli"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.basionym is not None
    assert result.basionym.name == "Bacterium coli"
    assert result.type_taxon is not None
    assert result.type_taxon.name == "Escherichia coli ATCC 11775"
    assert result.type_taxon.rank == "sous-espèce"
    assert result.subtaxa is not None
    assert [t.name for t in result.subtaxa.items] == ["Escherichia coli subsp. foo"]

    assert adapter.max_concurrent >= 2


@pytest.mark.asyncio
async def test_collect_classification_walks_ancestors_to_domain():
    module = LpsnModule(adapter=FakeLpsnAdapter([776], RECORDS_BY_ID))
    struct = Struct(taxon=TaxonInfo(name="Escherichia coli"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "LPSN"
    assert result.kingdom == "bactérie"
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == ["Escherichia", "Enterobacteriaceae"]
    assert result.original_publication == "Migula, W. 1895. Bacteriaceae."
    assert result.links["lpsn"]["id"] == "escherichia-coli"
    assert result.links["lpsn"]["url"] == "https://lpsn.dsmz.de/species/escherichia-coli"

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{LPSN | espèce | escherichia-coli | ''Escherichia coli''")
    assert module.debug_link(result) == (
        "<a href='https://lpsn.dsmz.de/species/escherichia-coli' target='_blank' "
        "rel='noopener noreferrer'>LPSN</a>"
    )


@pytest.mark.asyncio
async def test_collect_falls_back_to_record_id_url_without_monomial():
    record = {**ESCHERICHIA_COLI, "monomial": None}
    module = LpsnModule(adapter=FakeLpsnAdapter([776], {**RECORDS_BY_ID, 776: record}))
    struct = Struct(taxon=TaxonInfo(name="Escherichia coli"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["lpsn"]["id"] == 776
    assert result.links["lpsn"]["url"] == "https://lpsn.dsmz.de/taxon/776"


@pytest.mark.asyncio
async def test_collect_synonym_redirects_to_accepted_when_classifying():
    synonym = {
        **ESCHERICHIA_COLI,
        "id": 999,
        "full_name": "Bacterium coli",
        "lpsn_correct_name_id": 776,
    }
    module = LpsnModule(adapter=FakeLpsnAdapter([999], {**RECORDS_BY_ID, 999: synonym}))
    struct = Struct(taxon=TaxonInfo(name="Bacterium coli"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Escherichia coli"
    assert result.classification == "LPSN"


@pytest.mark.asyncio
async def test_collect_synonym_enrichment_flags_without_redirect():
    synonym = {
        **ESCHERICHIA_COLI,
        "id": 999,
        "full_name": "Bacterium coli",
        "lpsn_correct_name_id": 776,
    }
    module = LpsnModule(adapter=FakeLpsnAdapter([999], {**RECORDS_BY_ID, 999: synonym}))
    struct = Struct(taxon=TaxonInfo(name="Bacterium coli"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["lpsn"]["synonym"] is True


@pytest.mark.asyncio
async def test_collect_not_found():
    module = LpsnModule(adapter=FakeLpsnAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
