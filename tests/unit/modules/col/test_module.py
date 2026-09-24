"""Tests de ColModule : classification complète via ChecklistBank 3LXR (résolution partagée
avec GbifModule, voir col_xr/lookup.py, déjà testée dans tests/unit/modules/col_xr/), synonymes,
sous-taxons, noms vernaculaires."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.col.module import ColModule
from organon.modules.col_xr.adapter import ColXrAdapter

APIS_CLASSIFICATION = [
    {"id": "K1", "name": "Animalia", "rank": "kingdom"},
    {"id": "P1", "name": "Arthropoda", "rank": "phylum"},
    {"id": "C1", "name": "Insecta", "rank": "class"},
    {"id": "O1", "name": "Hymenoptera", "rank": "order"},
    {"id": "F1", "name": "Apidae", "rank": "family"},
    {"id": "G1", "name": "Apis", "rank": "genus"},
    {"id": "9082C709", "name": "Apis mellifera", "rank": "species"},
]

APIS_MELLIFERA = {
    "id": "9082C709",
    "usage": {
        "status": "accepted",
        "name": {
            "scientificName": "Apis mellifera",
            "authorship": "Linnaeus, 1758",
            "rank": "species",
        },
        "extinct": False,
    },
    "classification": APIS_CLASSIFICATION,
    "vernacularNames": [
        {"language": "fra", "name": "Abeille domestique"},
        {"language": "eng", "name": "Honey bee"},
    ],
}


class FakeColXrAdapter(ColXrAdapter):
    def __init__(
        self,
        by_name: dict[str, list[dict]],
        children: list[dict] | None = None,
        synonyms: dict[str, list[dict]] | None = None,
    ):
        self._by_name = by_name
        self._children = children or []
        self._synonyms = synonyms or {}

    async def search(self, taxon: str, *, exact: bool = True) -> list[dict]:
        return self._by_name.get(taxon, [])

    async def children_page(self, taxon_id: str, offset: int = 0) -> dict:
        return {"result": self._children, "last": True}

    async def synonyms(self, taxon_id: str) -> dict:
        return self._synonyms


@pytest.mark.asyncio
async def test_collect_classification_full():
    module = ColModule(
        adapter=FakeColXrAdapter(
            {"Apis mellifera": [APIS_MELLIFERA]},
            children=[
                {
                    "name": "Apis mellifera ligustica",
                    "rank": "subspecies",
                    "authorship": "Spinola, 1806",
                    "status": "accepted",
                    "labelHtml": "Apis mellifera ligustica",
                }
            ],
            synonyms={
                "homotypic": [{"name": {"scientificName": "Apis mellifica", "rank": "species"}}]
            },
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "CatalogueofLife"
    assert result.kingdom == "animal"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Linnaeus, 1758"
    rank_names = ["Apis", "Apidae", "Hymenoptera", "Insecta", "Arthropoda"]
    assert [r.name for r in result.ranks] == rank_names
    assert result.vernacular["CatalogueofLife"] == {
        "fr": ["Abeille domestique"],
        "en": ["Honey bee"],
    }
    assert result.subtaxa.items[0].name == "Apis mellifera ligustica"
    assert result.synonyms.items[0].name == "Apis mellifica"

    bioref = module.render_bioref(result)
    prefix = "{{CatalogueofLife | 9082C709 | ''Apis mellifera'' Linnaeus, 1758 | consulté le="
    assert bioref.startswith(prefix)
    assert module.debug_link(result) == (
        "<a href='https://www.catalogueoflife.org/data/taxon/9082C709' target='_blank' "
        "rel='noopener noreferrer'>CoL</a>"
    )


@pytest.mark.asyncio
async def test_collect_synonym_redirects_when_classifying():
    synonym = {
        "id": "SYN1",
        "usage": {
            "status": "synonym",
            "name": {"scientificName": "Apis mellifica", "authorship": "L.", "rank": "species"},
            "accepted": {"name": {"scientificName": "Apis mellifera"}},
        },
        "classification": [],
    }
    module = ColModule(
        adapter=FakeColXrAdapter(
            {"Apis mellifica": [synonym], "Apis mellifera": [APIS_MELLIFERA]}
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifica"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Apis mellifera"
    assert result.classification == "CatalogueofLife"


@pytest.mark.asyncio
async def test_collect_synonym_enrichment_flags_without_redirect():
    synonym = {
        "id": "SYN1",
        "usage": {
            "status": "synonym",
            "name": {"scientificName": "Apis mellifica", "authorship": "L.", "rank": "species"},
            "accepted": {"name": {"scientificName": "Apis mellifera"}},
        },
        "classification": [],
    }
    module = ColModule(adapter=FakeColXrAdapter({"Apis mellifica": [synonym]}))
    struct = Struct(taxon=TaxonInfo(name="Apis mellifica"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["col"]["synonym"] is True
    assert result.links["col"]["detected_status"] == "synonyme"


@pytest.mark.asyncio
async def test_collect_children_skips_child_without_rank():
    module = ColModule(
        adapter=FakeColXrAdapter(
            {"Apis mellifera": [APIS_MELLIFERA]},
            children=[
                {
                    "name": "Apis mellifera malformee",
                    "status": "accepted",
                    "labelHtml": "Apis mellifera malformee",
                },
                {
                    "name": "Apis mellifera ligustica",
                    "rank": "subspecies",
                    "authorship": "Spinola, 1806",
                    "status": "accepted",
                    "labelHtml": "Apis mellifera ligustica",
                },
            ],
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert [c.name for c in result.subtaxa.items] == ["Apis mellifera ligustica"]


@pytest.mark.asyncio
async def test_collect_not_found():
    module = ColModule(adapter=FakeColXrAdapter({}))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


def _subgenus_record(col_name: str) -> dict:
    return {
        "id": "44NK3",
        "usage": {
            "status": "accepted",
            "name": {
                "scientificName": col_name,
                "authorship": "Linnaeus, 1758",
                "rank": "species",
            },
        },
        "classification": APIS_CLASSIFICATION,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "col_name"),
    [
        ("Mus musculus", "Mus (Mus) musculus"),
        ("Drosophila melanogaster", "Drosophila (Sophophora) melanogaster"),
        ("Aedes aegypti", "Aedes (Stegomyia) aegypti"),
    ],
)
async def test_classification_name_without_subgenus(requested, col_name):
    """Le nom porté par `struct.taxon` est relu par les modules d'enrichissement (recherche par
    nom) : il ne doit pas contenir le sous-genre que CoL ajoute, ni titre de page fantaisiste."""
    module = ColModule(adapter=FakeColXrAdapter({requested: [_subgenus_record(col_name)]}))
    result = await module.collect(
        Struct(taxon=TaxonInfo(name=requested)), is_classification=True, options=GenerateOptions()
    )
    assert result is not None
    assert result.taxon.name == requested
    assert result.links["col"]["name"] == col_name


@pytest.mark.asyncio
async def test_classification_subgenus_itself_kept():
    module = ColModule(
        adapter=FakeColXrAdapter({"Mus (Mus)": [_subgenus_record("Mus (Mus)")]})
    )
    result = await module.collect(
        Struct(taxon=TaxonInfo(name="Mus (Mus)")), is_classification=True, options=GenerateOptions()
    )
    assert result is not None
    assert result.taxon.name == "Mus (Mus)"
