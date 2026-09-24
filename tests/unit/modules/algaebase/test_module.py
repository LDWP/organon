"""Tests de AlgaeBaseModule : trois formes de recherche selon le nombre de mots du taxon
(espèce >=2 mots, puis genre, puis repli "rang supérieur" — voir module.py), jeton de session
(`fetch_key`) requis avant tout appel."""

from __future__ import annotations

import asyncio

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.algaebase.module import AlgaeBaseModule

_ECTOCARPUS_CLASSIFICATION = [
    {"dwc:taxonRank": "Kingdom", "dwc:scientificName": "Chromista"},
    {"dwc:taxonRank": "Phylum", "dwc:scientificName": "Ochrophyta"},
    {"dwc:taxonRank": "Class", "dwc:scientificName": "Phaeophyceae"},
    {"dwc:taxonRank": "Order", "dwc:scientificName": "Ectocarpales"},
    {"dwc:taxonRank": "Family", "dwc:scientificName": "Ectocarpaceae"},
    {"dwc:taxonRank": "Genus", "dwc:scientificName": "Ectocarpus", "dwc:taxonID": 1234},
]


class FakeAlgaeBaseAdapter:
    def __init__(
        self,
        key: str | None = "session-key",
        species_pages: dict[str, dict] | None = None,
        species_details: dict[int, dict] | None = None,
        genus_search: dict | None = None,
        genus_details: dict[int, dict] | None = None,
        taxonomy_search: dict | None = None,
        taxonomy_details: dict[int, dict] | None = None,
        page_details: dict[int, dict] | None = None,
    ):
        self._key = key
        self._species_pages = species_pages or {}
        self._species_details = species_details or {}
        self._genus_search = genus_search
        self._genus_details = genus_details or {}
        self._taxonomy_search = taxonomy_search
        self._taxonomy_details = taxonomy_details or {}
        self._page_details = page_details or {}

    async def fetch_key(self) -> str | None:
        return self._key

    doi_citations: dict[str, str] = {}

    async def resolve_doi_citation(self, doi: str) -> str | None:
        return self.doi_citations.get(doi)

    async def search_species_page(self, key: str, taxon: str, offset: int) -> dict | None:
        if offset == 0:
            return self._species_pages.get(taxon)
        return {"result": [], "_pagination": {"_total_number_of_results": 0}}

    async def species_detail(self, key: str, accepted_id: int) -> dict | None:
        detail = self._species_details.get(accepted_id)
        return {"details": detail} if detail else None

    async def genus_detail(self, key: str, genus_id: int) -> dict | None:
        return self._genus_details.get(genus_id)

    async def taxonomy_page_detail(self, key: str, taxon_id) -> dict | None:
        return self._page_details.get(taxon_id)

    async def search_genus(self, key: str, taxon: str) -> dict | None:
        return self._genus_search

    async def taxonomy_detail(self, key: str, taxon_id) -> dict | None:
        return self._taxonomy_details.get(taxon_id)

    async def search_taxonomy(self, key: str, taxon: str) -> dict | None:
        return self._taxonomy_search


@pytest.mark.asyncio
async def test_collect_species_classification_full():
    taxon = "Ectocarpus siliculosus"
    initial_hit = {
        "dwc:scientificName": "Ectocarpus siliculosus Dillwyn",
        "dwc:scientificNameAuthorship": "Dillwyn",
        "dwc:acceptedNameUsageID": 5678,
    }
    full_detail = {
        "dwc:taxonRank": "species",
        "dwc:acceptedNameUsageID": 5678,
        "genusID": 1234,
        "dwc:scientificNameAuthorship": "Dillwyn",
        "dwc:namePublishedInYear": "1809",
        "dwc:isMarine": "Y",
        "dcterms:bibliographicCitation": "Some citation <i>Ectocarpus</i>. 1809.",
        "nameOrigin": "From Greek ektos (outside).",
    }
    module = AlgaeBaseModule(
        adapter=FakeAlgaeBaseAdapter(
            species_pages={
                taxon: {
                    "result": [initial_hit],
                    "_pagination": {"_total_number_of_results": 1},
                }
            },
            species_details={5678: full_detail},
            genus_details={1234: {"classification": _ECTOCARPUS_CLASSIFICATION}},
            page_details={5678: {"details": {"description": "Filamentous brown alga."}}},
        )
    )
    struct = Struct(taxon=TaxonInfo(name=taxon))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "AlgaeBASE"
    assert result.kingdom == "algue"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Dillwyn, 1809"
    assert result.links["algaebase"]["id"] == 5678
    assert [r.name for r in result.ranks] == [
        "Ectocarpus",
        "Ectocarpaceae",
        "Ectocarpales",
        "Phaeophyceae",
        "Ochrophyta",
        "Chromista",
    ]
    assert result.original_publication == "Some citation ''Ectocarpus''. 1809."
    assert result.etymology.text == "''From Greek ektos (outside)''"
    assert result.description["AlgaeBASE"] == [
        "Cette espèce est marine",
        "''Filamentous brown alga.''",
    ]

    bioref = module.render_bioref(result)
    prefix = "{{AlgaeBASE espèce | 5678 | ''Ectocarpus siliculosus'' Dillwyn, 1809 |"
    assert bioref.startswith(prefix)
    assert module.debug_link(result) == (
        "<a href='https://www.algaebase.org/search/species/detail/?species_id=5678' "
        "target='_blank' rel='noopener noreferrer'>AlgaeBase</a>"
    )


@pytest.mark.asyncio
async def test_collect_species_genus_and_page_detail_run_concurrently():
    """genus_detail() et taxonomy_page_detail() portent sur des ids indépendants (genusID vs
    dwc:acceptedNameUsageID) : ils doivent partir en parallèle via asyncio.gather. Chaque
    variante se bloque tant que l'autre n'a pas démarré, sous un délai borné : un retour à un
    await série ferait échouer le test par TimeoutError au lieu de rester bloqué indéfiniment."""
    taxon = "Ectocarpus siliculosus"
    initial_hit = {
        "dwc:scientificName": "Ectocarpus siliculosus Dillwyn",
        "dwc:scientificNameAuthorship": "Dillwyn",
        "dwc:acceptedNameUsageID": 5678,
    }
    full_detail = {
        "dwc:taxonRank": "species",
        "dwc:acceptedNameUsageID": 5678,
        "genusID": 1234,
    }

    class ConcurrencyProbeAdapter(FakeAlgaeBaseAdapter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.genus_started = asyncio.Event()
            self.page_started = asyncio.Event()

        async def genus_detail(self, key: str, genus_id: int) -> dict | None:
            self.genus_started.set()
            await asyncio.wait_for(self.page_started.wait(), timeout=1)
            return await super().genus_detail(key, genus_id)

        async def taxonomy_page_detail(self, key: str, taxon_id) -> dict | None:
            self.page_started.set()
            await asyncio.wait_for(self.genus_started.wait(), timeout=1)
            return await super().taxonomy_page_detail(key, taxon_id)

    module = AlgaeBaseModule(
        adapter=ConcurrencyProbeAdapter(
            species_pages={
                taxon: {"result": [initial_hit], "_pagination": {"_total_number_of_results": 1}}
            },
            species_details={5678: full_detail},
            genus_details={1234: {"classification": _ECTOCARPUS_CLASSIFICATION}},
            page_details={5678: {"details": {"description": "Filamentous brown alga."}}},
        )
    )
    struct = Struct(taxon=TaxonInfo(name=taxon))

    result = await asyncio.wait_for(
        module.collect(struct, is_classification=True, options=GenerateOptions()), timeout=2
    )

    assert result is not None
    assert result.description["AlgaeBASE"] == ["''Filamentous brown alga.''"]


@pytest.mark.asyncio
async def test_collect_species_skips_page_detail_when_accepted_id_missing():
    """Quand la résolution de synonyme échoue, dwc:acceptedNameUsageID reste absent : blob["id"]
    est None. taxonomy_page_detail() ne doit jamais être appelé avec cet id, sous peine de taper
    /taxonomy/None/detail côté API (même défaut que species_detail(), corrigé en 226f768)."""
    taxon = "Ectocarpus siliculosus"
    hit_without_accepted_id = {
        "dwc:scientificName": "Ectocarpus siliculosus Dillwyn",
        "dwc:scientificNameAuthorship": "Dillwyn",
        "dwc:taxonRank": "species",
        "genusID": 1234,
    }

    class RecordingAdapter(FakeAlgaeBaseAdapter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.page_detail_calls: list = []

        async def taxonomy_page_detail(self, key: str, taxon_id) -> dict | None:
            self.page_detail_calls.append(taxon_id)
            return await super().taxonomy_page_detail(key, taxon_id)

    adapter = RecordingAdapter(
        species_pages={
            taxon: {
                "result": [hit_without_accepted_id],
                "_pagination": {"_total_number_of_results": 1},
            }
        },
        genus_details={1234: {"classification": _ECTOCARPUS_CLASSIFICATION}},
    )
    module = AlgaeBaseModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name=taxon))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.links["algaebase"]["id"] is None
    assert adapter.page_detail_calls == []


@pytest.mark.asyncio
async def test_collect_genus_classification():
    genus_hit = {
        "dwc:scientificName": "Ectocarpus",
        "dwc:taxonRank": "genus",
        "dwc:acceptedNameUsageID": 1234,
    }
    module = AlgaeBaseModule(
        adapter=FakeAlgaeBaseAdapter(
            genus_search={"result": [genus_hit], "_pagination": {"_total_number_of_results": 1}},
            genus_details={1234: {"classification": _ECTOCARPUS_CLASSIFICATION}},
            page_details={1234: {"details": {}}},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Ectocarpus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "AlgaeBASE"
    assert result.kingdom == "algue"
    assert result.links["algaebase"]["id"] == 1234
    # L'entrée "genre" de la chaîne (le taxon lui-même) est exclue de struct.ranks.
    assert [r.name for r in result.ranks] == [
        "Ectocarpaceae",
        "Ectocarpales",
        "Phaeophyceae",
        "Ochrophyta",
        "Chromista",
    ]


@pytest.mark.asyncio
async def test_collect_superior_rank_fallback_when_genus_search_fails():
    family_hit = {
        "dwc:scientificName": "Ectocarpaceae",
        "dwc:taxonRank": "family",
        "dwc:taxonID": 999,
    }
    module = AlgaeBaseModule(
        adapter=FakeAlgaeBaseAdapter(
            genus_search=None,
            taxonomy_search={
                "result": [family_hit],
                "_pagination": {"_total_number_of_results": 1},
            },
            taxonomy_details={
                999: {
                    "higherTaxa": [
                        {"dwc:taxonRank": "Kingdom", "dwc:scientificName": "Chromista"},
                        {"dwc:taxonRank": "Phylum", "dwc:scientificName": "Ochrophyta"},
                    ]
                }
            },
            page_details={999: {"details": {}}},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Ectocarpaceae"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.links["algaebase"]["id"] == 999
    assert result.kingdom == "algue"
    assert [r.name for r in result.ranks] == ["Ochrophyta", "Chromista"]


@pytest.mark.asyncio
async def test_collect_returns_none_without_session_key():
    module = AlgaeBaseModule(adapter=FakeAlgaeBaseAdapter(key=None))
    struct = Struct(taxon=TaxonInfo(name="Ectocarpus siliculosus"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = AlgaeBaseModule(
        adapter=FakeAlgaeBaseAdapter(
            species_pages={
                "Nonexistentgenusxyz zzz": {
                    "result": [],
                    "_pagination": {"_total_number_of_results": 0},
                }
            },
            genus_search={"result": [], "_pagination": {"_total_number_of_results": 0}},
            taxonomy_search={"result": [], "_pagination": {"_total_number_of_results": 0}},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent():
    module = AlgaeBaseModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("citation", "expected"),
    [
        (
            "Poinar 1975. https://doi.org/10.1163/187529275X00239",
            "{{Article | titre=T | périodique=P | date=1975}} ([http://x/p.pdf PDF])",
        ),
        (
            "Dillwyn 1809. <i>Ectocarpus</i>.",
            "Dillwyn 1809. ''Ectocarpus''. ([http://x/p.pdf PDF])",
        ),
    ],
)
async def test_collect_species_bibliographic_citation_resolves_doi(citation, expected):
    taxon = "Ectocarpus siliculosus"
    hit = {
        "dwc:scientificName": "Ectocarpus siliculosus Dillwyn",
        "dwc:acceptedNameUsageID": 5678,
        "dwc:scientificNameAuthorship": "Dillwyn",
    }
    detail = {
        "dwc:taxonRank": "species",
        "dwc:acceptedNameUsageID": 5678,
        "genusID": 1234,
        "dcterms:bibliographicCitation": citation,
        "pdfs": [{"pdf_url": "http://x/p.pdf"}],
    }
    adapter = FakeAlgaeBaseAdapter(
        species_pages={taxon: {"result": [hit], "_pagination": {"_total_number_of_results": 1}}},
        species_details={5678: detail},
        genus_details={1234: {"classification": _ECTOCARPUS_CLASSIFICATION}},
    )
    adapter.doi_citations = {
        "10.1163/187529275X00239": "{{Article | titre=T | périodique=P | date=1975}}"
    }
    module = AlgaeBaseModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name=taxon))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.original_publication == expected


@pytest.mark.asyncio
async def test_collect_species_detail_page_publication_resolves_doi():
    taxon = "Ectocarpus siliculosus"
    hit = {
        "dwc:scientificName": "Ectocarpus siliculosus Dillwyn",
        "dwc:acceptedNameUsageID": 5678,
        "dwc:scientificNameAuthorship": "Dillwyn",
    }
    detail = {
        "dwc:taxonRank": "species",
        "dwc:acceptedNameUsageID": 5678,
        "dwc:scientificNameAuthorship": "Dillwyn",
        "genusID": 1234,
    }
    adapter = FakeAlgaeBaseAdapter(
        species_pages={taxon: {"result": [hit], "_pagination": {"_total_number_of_results": 1}}},
        species_details={5678: detail},
        genus_details={1234: {"classification": _ECTOCARPUS_CLASSIFICATION}},
        page_details={
            5678: {
                "details": {"originalPublicationRef": "Poinar 1975 doi:10.1163/187529275X00239"}
            }
        },
    )
    adapter.doi_citations = {"10.1163/187529275X00239": "{{Article | titre=T}}"}
    module = AlgaeBaseModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name=taxon))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.original_publication == "{{Article | titre=T}}"
