"""Tests du module MDD : interroge ChecklistBank dataset `9802` (même schéma de réponse que
`col`/`bryonames`, seul le dataset change). Ornithorhynchus anatinus (accepté) et Ornithorhynchus
agilis (synonyme hétérotypique) servent de taxons de référence."""

import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.mdd.module import MddModule

SEARCH_URL = "https://api.checklistbank.org/dataset/9802/nameusage/search"
CHILDREN_URL = "https://api.checklistbank.org/dataset/9802/tree/1000001/children"
SYNONYMS_URL = "https://api.checklistbank.org/dataset/9802/taxon/1000001/synonyms"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": "1000001",
            "classification": [
                {"name": "Mammalia", "rank": "class"},
                {"name": "Yinotheria", "rank": "subclass"},
                {"name": "Monotremata", "rank": "order"},
                {"name": "Ornithorhynchidae", "rank": "family"},
                {"name": "Ornithorhynchus", "rank": "genus"},
                {"name": "Ornithorhynchus anatinus", "rank": "species", "id": "1000001"},
            ],
            "usage": {
                "status": "accepted",
                "extinct": False,
                "name": {
                    "scientificName": "Ornithorhynchus anatinus",
                    "authorship": "(G. K. Shaw, 1799)",
                    "rank": "species",
                    "genus": "Ornithorhynchus",
                    "specificEpithet": "anatinus",
                },
            },
        }
    ]
}

_SYNONYM_PAYLOAD = {
    "result": [
        {
            "id": "100014420",
            "usage": {
                "status": "synonym",
                "name": {
                    "scientificName": "Ornithorhynchus agilis",
                    "authorship": "De Vis, 1885",
                    "rank": "species",
                    "genus": "Ornithorhynchus",
                    "specificEpithet": "agilis",
                },
                "accepted": {"name": {"scientificName": "Ornithorhynchus anatinus"}},
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_mdd_enrichment_only_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Ornithorhynchus anatinus"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )

        module = MddModule(adapter=ChecklistBankAdapter("9802"))
        struct = Struct(
            taxon=TaxonInfo(name="Ornithorhynchus anatinus", rank="espèce"), kingdom="animal"
        )
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["mdd"]
    assert data["id"] == "1000001"
    assert data["name"] == "Ornithorhynchus anatinus"
    assert data["author"] == "(G. K. Shaw, 1799)"
    assert data["rank"] == "espèce"
    assert data["genus"] == "Ornithorhynchus"
    assert data["epithet"] == "anatinus"
    assert "synonyme" not in data
    # Enrichissement seul : pas d'effet sur la classification.
    assert result.classification == ""
    assert result.ranks == []

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{MDD | Ornithorhynchus | anatinus | 1000001 | "
        "''Ornithorhynchus anatinus'' (G. K. Shaw, 1799) | consulté le="
        + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        "<a href='https://www.mammaldiversity.org/taxon/1000001' "
        "target='_blank' rel='noopener noreferrer'>MDD</a>"
    )


@pytest.mark.asyncio
async def test_mdd_classification_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Ornithorhynchus anatinus"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )
        router.get(CHILDREN_URL).respond(
            200,
            json={
                "result": [
                    {
                        "name": "Ornithorhynchus anatinus triton",
                        "rank": "subspecies",
                        "authorship": "Wakefield, 1963",
                        "status": "accepted",
                        "labelHtml": "<i>Ornithorhynchus anatinus triton</i> Wakefield, 1963",
                    },
                    {"name": "Non classé", "rank": "unranked", "status": "accepted"},
                    {"name": "Nom douteux", "rank": "subspecies", "status": "provisional"},
                ],
                "last": True,
            },
        )
        router.get(SYNONYMS_URL).respond(
            200,
            json={
                "homotypic": [],
                "heterotypic": [
                    {
                        "name": {
                            "scientificName": "Ornithorhynchus agilis",
                            "authorship": "De Vis, 1885",
                            "rank": "species",
                        }
                    }
                ],
            },
        )

        module = MddModule(adapter=ChecklistBankAdapter("9802"))
        struct = Struct(taxon=TaxonInfo(name="Ornithorhynchus anatinus"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == "MDD"
    assert result.classification_taxobox == "MDD"
    assert result.kingdom == "animal"
    assert result.taxon.author == "(G. K. Shaw, 1799)"
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == [
        "Ornithorhynchus",
        "Ornithorhynchidae",
        "Monotremata",
        "Yinotheria",
        "Mammalia",
    ]

    assert result.subtaxa is not None
    assert result.subtaxa.source == "MDD"
    assert [s.name for s in result.subtaxa.items] == ["Ornithorhynchus anatinus triton"]

    assert result.synonyms is not None
    assert result.synonyms.source == "MDD"
    assert result.synonyms.items[0].name == "Ornithorhynchus agilis"


@pytest.mark.asyncio
async def test_mdd_synonym_marked_without_following():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Ornithorhynchus agilis"}).respond(
            200, json=_SYNONYM_PAYLOAD
        )

        module = MddModule(adapter=ChecklistBankAdapter("9802"))
        struct = Struct(
            taxon=TaxonInfo(name="Ornithorhynchus agilis", rank="espèce"), kingdom="animal"
        )
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["mdd"]
    assert data["name"] == "Ornithorhynchus agilis"
    assert data["synonym"] is True

    bioref = module.render_bioref(result)
    assert bioref.endswith("<small>(non valide)</small>")


@pytest.mark.asyncio
async def test_mdd_classification_follows_synonym_to_accepted_target():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Ornithorhynchus agilis"}).respond(
            200, json=_SYNONYM_PAYLOAD
        )
        router.get(SEARCH_URL, params={"q": "Ornithorhynchus anatinus"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )
        router.get(CHILDREN_URL).respond(200, json={"result": [], "last": True})
        router.get(SYNONYMS_URL).respond(200, json={"homotypic": [], "heterotypic": []})

        module = MddModule(adapter=ChecklistBankAdapter("9802"))
        struct = Struct(taxon=TaxonInfo(name="Ornithorhynchus agilis"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.taxon.name == "Ornithorhynchus anatinus"
    assert result.kingdom == "animal"
    assert result.classification == "MDD"


@pytest.mark.asyncio
async def test_mdd_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = MddModule(adapter=ChecklistBankAdapter("9802"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_mdd_render_bioref_genus_uses_mddsup():
    module = MddModule()
    struct = Struct(taxon=TaxonInfo(name="Ornithorhynchus", rank="genre"), kingdom="animal")
    struct.links["mdd"] = {"id": "xD", "name": "Ornithorhynchus", "rank": "genre"}

    bioref = module.render_bioref(struct)

    assert bioref.startswith("{{MDDsup | genre | Ornithorhynchus | consulté le=")
    # Le nom n'est pas pré-italicisé : c'est le modèle MDDsup qui le met en italique.
    assert "''" not in bioref


def test_mdd_render_bioref_generic_fallback_for_uncovered_rank():
    module = MddModule()
    struct = Struct(taxon=TaxonInfo(name="Mammalia", rank="classe"), kingdom="animal")
    struct.links["mdd"] = {"id": "x4", "name": "Mammalia", "rank": "classe"}

    bioref = module.render_bioref(struct)

    assert bioref.startswith(
        "{{Lien web | langue=en | titre=Mammalia | url=https://www.mammaldiversity.org/taxon/x4 "
        "| site=Mammal Diversity Database | consulté le="
    )


def test_mdd_render_bioref_absent():
    module = MddModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_mdd_debug_link_absent():
    module = MddModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None
