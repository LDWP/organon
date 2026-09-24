"""Tests de WscModule : classification espèce/sous-espèce à partir d'une ligne de l'export CSV
WSC, chaîne fixe Araneae/Arachnida/Arthropoda (absente du CSV, voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.wsc.module import WscModule

ACTINOPUS_ROW = {
    "speciesId": "6625",
    "family": "Actinopodidae",
    "genus": "Actinopus",
    "species": "caraiba",
    "subspecies": "",
    "author": "Simon",
    "year": "1889",
    "parentheses": "1",
}


class FakeWscAdapter:
    def __init__(self, row: dict | None):
        self._row = row

    async def search(self, name: str) -> dict | None:
        return self._row


@pytest.mark.asyncio
async def test_collect_classifies_species():
    module = WscModule(adapter=FakeWscAdapter(ACTINOPUS_ROW))
    struct = Struct(taxon=TaxonInfo(name="Actinopus caraiba"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "(Simon, 1889)"
    assert result.kingdom == "animal"
    assert result.classification == "WSC"
    assert [r.name for r in result.ranks] == [
        "Actinopus",
        "Actinopodidae",
        "Araneae",
        "Arachnida",
        "Arthropoda",
    ]


@pytest.mark.asyncio
async def test_collect_classifies_subspecies():
    row = {**ACTINOPUS_ROW, "subspecies": "meridionalis"}
    module = WscModule(adapter=FakeWscAdapter(row))
    struct = Struct(taxon=TaxonInfo(name="Actinopus caraiba meridionalis"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.rank == "sous-espèce"
    assert result.ranks[0].name == "Actinopus caraiba"
    assert result.ranks[0].rank == "espèce"


@pytest.mark.asyncio
async def test_collect_enrichment_only_does_not_set_rank():
    module = WscModule(adapter=FakeWscAdapter(ACTINOPUS_ROW))
    struct = Struct(taxon=TaxonInfo(name="Actinopus caraiba"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["wsc"] == {"id": "6625", "name": "Actinopus caraiba"}
    assert result.classification == ""


@pytest.mark.asyncio
async def test_collect_not_found():
    module = WscModule(adapter=FakeWscAdapter(None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


def test_debug_link():
    module = WscModule()
    struct = Struct(taxon=TaxonInfo(name="X"), links={"wsc": {"id": "6625", "name": "X"}})
    assert module.debug_link(struct) == (
        "<a href='https://wsc.nmbe.ch/species/6625' target='_blank' "
        "rel='noopener noreferrer'>WSC</a>"
    )
