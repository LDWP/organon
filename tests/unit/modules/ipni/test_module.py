"""Tests de IpniModule : enrichissement botanique pur, ne retient qu'un enregistrement de nom
(champ `name` présent) au nom exact, préférant celui marqué `inPowo` s'il existe (voir
module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.ipni.module import IpniModule


class FakeIpniAdapter:
    def __init__(self, results: list[dict], doi_citation: str | None = None):
        self._results = results
        self._doi_citation = doi_citation

    async def search(self, name: str) -> list[dict]:
        return self._results

    async def resolve_doi_citation(self, doi: str) -> str | None:
        return self._doi_citation


@pytest.mark.asyncio
async def test_collect_prefers_inpowo_record_among_homonyms():
    results = [
        {
            "name": "Quercus robur",
            "url": "/n/321116-2",
            "authors": "Asso",
            "publicationYear": "1779",
            "reference": "Syn. Stirp. Arag.: 105 (1779)",
        },
        {
            "name": "Quercus robur",
            "url": "/n/320035-2",
            "authors": "L.",
            "publicationYear": "1753",
            "inPowo": True,
            "reference": "Sp. Pl.: 996 (1753)",
        },
    ]
    module = IpniModule(adapter=FakeIpniAdapter(results))
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["ipni"]["id"] == "320035-2"
    assert result.links["ipni"]["author"] == "L., 1753"
    assert result.original_publication == "Sp. Pl.: 996 (1753)"

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{IPNI | 320035-2 | Quercus robur | L., 1753 | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://www.ipni.org/n/320035-2' target='_blank' "
        "rel='noopener noreferrer'>IPNI</a>"
    )


@pytest.mark.asyncio
async def test_collect_falls_back_to_first_exact_match_without_inpowo():
    results = [
        {"name": "Quercus robur", "url": "/n/1", "authors": "Asso", "reference": "ref A"},
        {"name": "Quercus robur", "url": "/n/2", "authors": "Pallas", "reference": "ref B"},
    ]
    module = IpniModule(adapter=FakeIpniAdapter(results))
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["ipni"]["id"] == "1"


@pytest.mark.asyncio
async def test_collect_resolves_doi_citation_from_remarks():
    results = [
        {
            "name": "Rafflesia consueloae",
            "url": "/n/999",
            "authors": "Galindon, Ong & Fernando",
            "remarks": "doi:10.3897/phytokeys.61.7295 The specific epithet honors ...",
            "reference": "PhytoKeys 61: 37 (2016)",
        }
    ]
    module = IpniModule(
        adapter=FakeIpniAdapter(results, doi_citation="PhytoKeys 61: 37–46 (2016) [enrichi]")
    )
    struct = Struct(taxon=TaxonInfo(name="Rafflesia consueloae"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.original_publication == "PhytoKeys 61: 37–46 (2016) [enrichi]"


@pytest.mark.asyncio
async def test_collect_ignores_non_name_records():
    # Un enregistrement de publication/auteur (pas de champ "name") : filtré, comme le nom exact
    # inexistant dans les résultats.
    results = [{"authors": "L.", "url": "/n/1"}]
    module = IpniModule(adapter=FakeIpniAdapter(results))
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = IpniModule(adapter=FakeIpniAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
