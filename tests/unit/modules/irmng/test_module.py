"""Tests de IrmngModule : même architecture que WoRMS (plateforme Aphia/VLIZ partagée, voir
module.py) — classification via arbre imbriqué coupé à hauteur du règne, suivi de synonyme par
valid_IRMNG_ID, repli généraliste."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.irmng.module import IrmngModule

CANIS_LUPUS = {
    "IRMNG_ID": 1279043,
    "scientificname": "Canis lupus",
    "rank": "Species",
    "authority": "Linnaeus, 1758",
    "kingdom": "Animalia",
    "status": "accepted",
    "valid_IRMNG_ID": 1279043,
}

CLASSIFICATION_TREE = {
    "scientificname": "Biota",
    "rank": "Superdomain",
    "child": {
        "scientificname": "Animalia",
        "rank": "Kingdom",
        "child": {
            "scientificname": "Chordata",
            "rank": "Phylum",
            "child": {
                "scientificname": "Mammalia",
                "rank": "Class",
                "child": {"scientificname": "Canis lupus", "rank": "Species", "child": None},
            },
        },
    },
}


class FakeIrmngAdapter:
    def __init__(
        self,
        records: list[dict],
        classification_tree: dict | None = None,
        vernaculars: list[dict] | None = None,
        original_description: str | None = None,
        synonyms: list[dict] | None = None,
        children: list[dict] | None = None,
        record_by_id_map: dict[int, dict] | None = None,
    ):
        self._records = records
        self._classification_tree = classification_tree
        self._vernaculars = vernaculars or []
        self._original_description = original_description
        self._synonyms = synonyms or []
        self._children = children or []
        self._record_by_id_map = record_by_id_map or {}

    async def records_by_name(self, name: str) -> list[dict]:
        return self._records

    async def record_by_id(self, irmng_id: int) -> dict | None:
        return self._record_by_id_map.get(irmng_id)

    async def classification_by_id(self, irmng_id: int) -> dict | None:
        return self._classification_tree

    async def vernaculars_by_id(self, irmng_id: int) -> list[dict]:
        return self._vernaculars

    async def original_description(self, irmng_id: int) -> str | None:
        return self._original_description

    doi_citations: dict[str, str] = {}

    async def resolve_doi_citation(self, doi: str) -> str | None:
        return self.doi_citations.get(doi)

    async def synonyms_by_id(self, irmng_id: int, offset: int = 1) -> list[dict]:
        return self._synonyms if offset == 1 else []

    async def children_by_id(self, irmng_id: int, offset: int = 1) -> list[dict]:
        return self._children if offset == 1 else []


@pytest.mark.asyncio
async def test_collect_classification_full():
    module = IrmngModule(
        adapter=FakeIrmngAdapter(
            [CANIS_LUPUS],
            classification_tree=CLASSIFICATION_TREE,
            vernaculars=[
                {"vernacular": "Loup gris", "language": "French"},
                {"vernacular": "Grey wolf", "language": "English"},
            ],
            original_description="Linnaeus, C. 1758. Systema naturae.",
            synonyms=[
                {"scientificname": "Canis lycaon", "authority": "Schreber", "rank": "Species"}
            ],
            children=[
                {
                    "scientificname": "Canis lupus arctos",
                    "authority": "Pocock",
                    "rank": "Subspecies",
                    "status": "accepted",
                }
            ],
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Canis lupus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "IRMNG"
    assert result.kingdom == "animal"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Linnaeus, 1758"
    assert [r.name for r in result.ranks] == ["Mammalia", "Chordata"]
    assert result.vernacular["IRMNG"] == {"fr": ["Loup gris"], "en": ["Grey wolf"]}
    assert result.original_publication == "Linnaeus, C. 1758. Systema naturae."
    assert result.synonyms.items[0].name == "Canis lycaon"
    assert result.subtaxa.items[0].name == "Canis lupus arctos"

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{IRMNG | 1279043 | ''Canis lupus'' Linnaeus, 1758 | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://www.irmng.org/aphia.php?p=taxdetails&id=1279043' target='_blank' "
        "rel='noopener noreferrer'>IRMNG</a>"
    )


@pytest.mark.asyncio
async def test_collect_synonym_redirects_to_accepted_when_classifying():
    synonym = {**CANIS_LUPUS, "IRMNG_ID": 999, "status": "unaccepted", "valid_IRMNG_ID": 1279043}
    module = IrmngModule(
        adapter=FakeIrmngAdapter(
            [synonym],
            classification_tree=CLASSIFICATION_TREE,
            record_by_id_map={1279043: CANIS_LUPUS},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Canis lycaon"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Canis lupus"


@pytest.mark.asyncio
async def test_collect_synonym_enrichment_flags_and_renders_non_valid():
    synonym = {**CANIS_LUPUS, "IRMNG_ID": 999, "status": "unaccepted", "valid_IRMNG_ID": 1279043}
    module = IrmngModule(adapter=FakeIrmngAdapter([synonym]))
    struct = Struct(taxon=TaxonInfo(name="Canis lycaon"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["irmng"]["synonym"] is True
    bioref = module.render_bioref(result)
    assert bioref.endswith("<small>(non valide)</small>")


@pytest.mark.asyncio
async def test_collect_marks_extinct_taxon():
    record = {**CANIS_LUPUS, "isExtinct": True}
    module = IrmngModule(adapter=FakeIrmngAdapter([record]))
    struct = Struct(taxon=TaxonInfo(name="Canis lupus"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["irmng"]["extinct"] is True


@pytest.mark.asyncio
async def test_collect_not_found():
    module = IrmngModule(adapter=FakeIrmngAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "Poinar 1975. https://doi.org/10.1163/187529275X00239",
            "{{Article | titre=T | périodique=P | date=1975}}",
        ),
        ("Linnaeus, C. 1758. Systema naturae.", "Linnaeus, C. 1758. Systema naturae."),
    ],
)
async def test_collect_original_publication_resolves_doi(description, expected):
    adapter = FakeIrmngAdapter([CANIS_LUPUS], original_description=description)
    adapter.doi_citations = {
        "10.1163/187529275X00239": "{{Article | titre=T | périodique=P | date=1975}}"
    }
    module = IrmngModule(adapter=adapter)
    struct = Struct(taxon=TaxonInfo(name="Canis lupus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.original_publication == expected
