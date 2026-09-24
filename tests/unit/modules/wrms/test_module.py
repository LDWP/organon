"""Tests de WrmsModule : classification via l'arbre imbriqué WoRMS (coupé à hauteur du règne,
voir filter_ancestors_above_kingdom), suivi de synonyme par valid_AphiaID, milieu terrestre/marin."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.wrms.module import WrmsModule

GADUS_MORHUA = {
    "AphiaID": 126436,
    "scientificname": "Gadus morhua",
    "rank": "Species",
    "authority": "Linnaeus, 1758",
    "kingdom": "Animalia",
    "status": "accepted",
    "valid_AphiaID": 126436,
    "isMarine": 1,
    "isTerrestrial": 0,
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
                "scientificname": "Actinopterygii",
                "rank": "Class",
                "child": {"scientificname": "Gadus morhua", "rank": "Species", "child": None},
            },
        },
    },
}


class FakeWrmsAdapter:
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

    async def records_by_name(self, name: str, marine_only: bool = False) -> list[dict]:
        return self._records

    async def record_by_id(self, aphia_id: int) -> dict | None:
        return self._record_by_id_map.get(aphia_id)

    async def classification_by_id(self, aphia_id: int) -> dict | None:
        return self._classification_tree

    async def vernaculars_by_id(self, aphia_id: int) -> list[dict]:
        return self._vernaculars

    async def original_description(self, aphia_id: int) -> str | None:
        return self._original_description

    async def synonyms_by_id(self, aphia_id: int, offset: int = 1) -> list[dict]:
        return self._synonyms if offset == 1 else []

    async def children_by_id(
        self, aphia_id: int, marine_only: bool = False, offset: int = 1
    ) -> list[dict]:
        return self._children if offset == 1 else []


@pytest.mark.asyncio
async def test_collect_classification_full():
    module = WrmsModule(
        adapter=FakeWrmsAdapter(
            [GADUS_MORHUA],
            classification_tree=CLASSIFICATION_TREE,
            vernaculars=[
                {"vernacular": "Morue de l'Atlantique", "language": "French", "language_code": "fra"},
                {"vernacular": "Atlantic cod", "language": "English", "language_code": "eng"},
                {"vernacular": "Kabeljauw", "language": "Dutch"},
                {"vernacular": "???", "language": "Dothraki"},
            ],
            original_description="Linnaeus, C. 1758. Systema naturae.",
            synonyms=[{"scientificname": "Gadus callarias", "authority": "L.", "rank": "Species"}],
            children=[
                {
                    "scientificname": "Gadus morhua morhua",
                    "authority": "L.",
                    "rank": "Subspecies",
                    "status": "accepted",
                }
            ],
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "WRMS"
    assert result.kingdom == "animal"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Linnaeus, 1758"
    assert result.habitat == "marin"
    assert [r.name for r in result.ranks] == ["Actinopterygii", "Chordata"]
    assert result.vernacular["WRMS"] == {
        "fr": ["Morue de l'Atlantique"],
        "en": ["Atlantic cod"],
        "nl": ["Kabeljauw"],
        "und": ["???"],
    }
    assert result.original_publication == "Linnaeus, C. 1758. Systema naturae."
    assert result.synonyms.items[0].name == "Gadus callarias"
    assert result.subtaxa.items[0].name == "Gadus morhua morhua"

    bioref = module.render_bioref(result)
    prefix = "{{WRMS espèce | 126436 | Gadus morhua | Linnaeus, 1758 | consulté le="
    assert bioref.startswith(prefix)
    assert module.debug_link(result) == (
        "<a href='https://www.marinespecies.org/aphia.php?p=taxdetails&id=126436' "
        "target='_blank' rel='noopener noreferrer'>WRMS</a>"
    )


@pytest.mark.asyncio
async def test_collect_enrichment_reports_kingdom_signal():
    module = WrmsModule(adapter=FakeWrmsAdapter([GADUS_MORHUA]))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["wrms"]["detected_kingdom"] == "animal"
    assert result.classification == ""


@pytest.mark.asyncio
async def test_collect_terrestrial_takes_priority_over_marine():
    record = {**GADUS_MORHUA, "isTerrestrial": 1, "isMarine": 1}
    module = WrmsModule(adapter=FakeWrmsAdapter([record]))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.habitat == "terrestre"


@pytest.mark.asyncio
async def test_collect_synonym_redirects_to_accepted_when_classifying():
    synonym = {**GADUS_MORHUA, "AphiaID": 999, "status": "unaccepted", "valid_AphiaID": 126436}
    accepted = {**GADUS_MORHUA}
    module = WrmsModule(
        adapter=FakeWrmsAdapter(
            [synonym],
            classification_tree=CLASSIFICATION_TREE,
            record_by_id_map={126436: accepted},
        )
    )
    struct = Struct(taxon=TaxonInfo(name="Gadus callarias"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Gadus morhua"
    assert result.classification == "WRMS"


@pytest.mark.asyncio
async def test_collect_synonym_enrichment_flags_without_redirect():
    synonym = {**GADUS_MORHUA, "AphiaID": 999, "status": "unaccepted", "valid_AphiaID": 126436}
    module = WrmsModule(adapter=FakeWrmsAdapter([synonym]))
    struct = Struct(taxon=TaxonInfo(name="Gadus callarias"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["wrms"]["synonym"] is True
    assert result.taxon.name == "Gadus callarias"  # pas de redirection en mode enrichissement


@pytest.mark.asyncio
async def test_collect_not_found():
    module = WrmsModule(adapter=FakeWrmsAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
