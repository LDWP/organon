"""Tests de IctvModule : classification de référence pour le domaine virus, lecture pure d'un
dataset embarqué (voir adapter.py) — double léger plutôt que le vrai TSV, pour isoler le test du
contenu du dataset."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.ictv.adapter import IctvRecord
from organon.modules.ictv.module import IctvModule

SARS_COV_2_RECORD = IctvRecord(
    ancestors=(
        ("Realm", "Riboviria"),
        ("Kingdom", "Orthornavirae"),
        ("Phylum", "Pisuviricota"),
        ("Class", "Pisoniviricetes"),
        ("Order", "Nidovirales"),
        ("Family", "Coronaviridae"),
        ("Genus", "Betacoronavirus"),
        ("Species", "Severe acute respiratory syndrome-related coronavirus"),
    ),
    ictv_id="202004036",
)

BETACORONAVIRUS_RECORD = IctvRecord(
    ancestors=SARS_COV_2_RECORD.ancestors[:-1], ictv_id=None
)


class FakeIctvAdapter:
    def __init__(self, records: dict[str, IctvRecord], children: dict[str, list[tuple[str, str]]]):
        self._records = {k.lower(): v for k, v in records.items()}
        self._children = children

    def find(self, name: str) -> IctvRecord | None:
        return self._records.get(name.lower())

    def children_of(self, name: str) -> list[tuple[str, str]]:
        return self._children.get(name, [])


@pytest.mark.asyncio
async def test_collect_classification_species_with_id():
    adapter = FakeIctvAdapter(
        {"Severe acute respiratory syndrome-related coronavirus": SARS_COV_2_RECORD}, {}
    )
    module = IctvModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name="Severe acute respiratory syndrome-related coronavirus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.kingdom == "virus"
    assert result.classification == "ICTV"
    assert result.taxon.rank == "espèce"
    assert result.links["ictv"]["id"] == "202004036"
    assert [r.name for r in result.ranks] == [
        "Betacoronavirus",
        "Coronaviridae",
        "Nidovirales",
        "Pisoniviricetes",
        "Pisuviricota",
        "Orthornavirae",
        "Riboviria",
    ]

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{ICTV | 202004036 | "
        "''Severe acute respiratory syndrome-related coronavirus'' |  | consulté le="
    )
    assert module.debug_link(result) == (
        "<a href='https://ictv.global/id/202004036' target='_blank' "
        "rel='noopener noreferrer'>ICTV</a>"
    )


@pytest.mark.asyncio
async def test_collect_classification_includes_children_when_present():
    adapter = FakeIctvAdapter(
        {"Betacoronavirus": BETACORONAVIRUS_RECORD},
        {"Betacoronavirus": [("Species", "Human coronavirus HKU1")]},
    )
    module = IctvModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name="Betacoronavirus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    # Pas d'ICTV_ID à ce rang (voir docstring module.py) : pas de lien dans struct.links.
    assert "id" not in result.links["ictv"]
    assert result.subtaxa is not None
    assert result.subtaxa.items[0].name == "Human coronavirus HKU1"


@pytest.mark.asyncio
async def test_collect_enrichment_only_does_not_touch_classification():
    adapter = FakeIctvAdapter(
        {"Severe acute respiratory syndrome-related coronavirus": SARS_COV_2_RECORD}, {}
    )
    module = IctvModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name="Severe acute respiratory syndrome-related coronavirus"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.classification == ""
    assert result.links["ictv"]["id"] == "202004036"


@pytest.mark.asyncio
async def test_collect_not_found():
    module = IctvModule(adapter=FakeIctvAdapter({}, {}))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent_without_id():
    module = IctvModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None
