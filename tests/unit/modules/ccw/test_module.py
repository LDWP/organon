"""Tests du module Checklist of the Collembola of the World (CCW) : interroge ChecklistBank
dataset `2130` (même schéma de réponse que `col`/`col_xr`/`wco`/`bryonames`, seul le dataset
change). Entomobrya nivalis (acceptée) et Isotoma olivacea (synonyme hétérotypique d'Isotoma
viridis) servent de taxons de référence."""

import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.ccw.module import CcwModule

SEARCH_URL = "https://api.checklistbank.org/dataset/2130/nameusage/search"
CHILDREN_URL = "https://api.checklistbank.org/dataset/2130/tree/entobrya-nivalis/children"
SYNONYMS_URL = "https://api.checklistbank.org/dataset/2130/taxon/entobrya-nivalis/synonyms"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": "entobrya-nivalis",
            "classification": [
                {"name": "Collembola", "rank": "class", "authorship": "Lubbock, 1870"},
                {"name": "Entomobryomorpha", "rank": "order", "authorship": "Börner, 1913"},
                {"name": "Entomobryoidea", "rank": "superfamily", "authorship": "Womersley, 1934"},
                {"name": "Entomobryidae", "rank": "family", "authorship": "Womersley, 1934"},
                {"name": "Entomobryinae", "rank": "subfamily", "authorship": "Schäffer, 1896"},
                {"name": "Entomobryini", "rank": "tribe", "authorship": "Börner, 1906"},
                {"name": "Entomobrya", "rank": "genus", "authorship": "Rondani, 1861"},
                {"name": "Entomobrya nivalis", "rank": "species", "id": "entobrya-nivalis"},
            ],
            "usage": {
                "status": "accepted",
                "link": "https://www.collembola.org/taxa/entoinae.htm",
                "name": {
                    "scientificName": "Entomobrya nivalis",
                    "authorship": "(Linnaeus, 1758)",
                    "rank": "species",
                },
            },
        }
    ]
}

_SYNONYM_PAYLOAD = {
    "result": [
        {
            "id": "isotoma-olivacea",
            "usage": {
                "status": "synonym",
                "name": {
                    "scientificName": "Isotoma olivacea",
                    "authorship": "Tullberg, 1871",
                    "rank": "species",
                },
                "accepted": {"id": "isotoma-viridis", "name": {"scientificName": "Isotoma viridis"}},
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_ccw_enrichment_only_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Entomobrya nivalis"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Entomobrya nivalis", rank="espèce"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["ccw"]
    assert data["id"] == "entobrya-nivalis"
    assert data["name"] == "Entomobrya nivalis"
    assert data["author"] == "(Linnaeus, 1758)"
    assert data["rank"] == "espèce"
    assert "synonyme" not in data
    # Enrichissement seul : pas d'effet sur la classification.
    assert result.classification == ""
    assert result.ranks == []

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{Lien web | langue=en | titre=''Entomobrya nivalis'' (Linnaeus, 1758) | "
        "url=https://www.collembola.org/taxa/entoinae.htm | "
        "site=Checklist of the Collembola of the World | consulté le="
        + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        "<a href='https://www.collembola.org/taxa/entoinae.htm' "
        "target='_blank' rel='noopener noreferrer'>CCW</a>"
    )


@pytest.mark.asyncio
async def test_ccw_render_bioref_none_when_no_link():
    payload = {
        "result": [
            {
                **_ACCEPTED_PAYLOAD["result"][0],
                "usage": {**_ACCEPTED_PAYLOAD["result"][0]["usage"], "link": None},
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Entomobrya nivalis"}).respond(200, json=payload)

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Entomobrya nivalis", rank="espèce"), kingdom="animal")

        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert module.render_bioref(result) is None
    assert "checklistbank.org/dataset/2130/taxon/entobrya-nivalis" in module.debug_link(result)


@pytest.mark.asyncio
async def test_ccw_synonym_borrows_accepted_taxon_link():
    accepted_id = "isotoma|viridis"
    payload = {
        "result": [
            {
                **_SYNONYM_PAYLOAD["result"][0],
                "usage": {
                    **_SYNONYM_PAYLOAD["result"][0]["usage"],
                    "link": None,
                    "accepted": {"id": accepted_id, "name": {"scientificName": "Isotoma viridis"}},
                },
            }
        ]
    }
    accepted = {"link": "https://www.collembola.org/taxa/isotinae.htm"}
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Isotoma olivacea"}).respond(200, json=payload)
        router.get(
            "https://api.checklistbank.org/dataset/2130/taxon/isotoma%7Cviridis"
        ).respond(200, json=accepted)

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Isotoma olivacea", rank="espèce"), kingdom="animal")

        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    bioref = module.render_bioref(result)
    assert "url=https://www.collembola.org/taxa/isotinae.htm" in bioref
    assert "(non valide)" in bioref


@pytest.mark.asyncio
async def test_ccw_synonym_without_accepted_link_has_no_bioref():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Isotoma olivacea"}).respond(200, json=_SYNONYM_PAYLOAD)
        router.get("https://api.checklistbank.org/dataset/2130/taxon/isotoma-viridis").respond(
            200, json={"link": None}
        )

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Isotoma olivacea", rank="espèce"), kingdom="animal")

        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert module.render_bioref(result) is None


@pytest.mark.asyncio
async def test_ccw_classification_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Entomobrya nivalis"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )
        router.get(CHILDREN_URL).respond(
            200,
            json={
                "result": [
                    {
                        "name": "Entomobrya nivalis f. montana",
                        "rank": "form",
                        "authorship": "Stach",
                        "status": "accepted",
                        "labelHtml": "<i>Entomobrya nivalis f. montana</i> Stach",
                    },
                    {"name": "Non classé", "rank": "unranked", "status": "accepted"},
                    {"name": "Nom douteux", "rank": "species", "status": "provisional"},
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
                            "scientificName": "Isotoma nivalis",
                            "authorship": "Linnaeus, 1758",
                            "rank": "species",
                        }
                    }
                ],
            },
        )

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Entomobrya nivalis"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == "CCW"
    assert result.classification_taxobox == "CCW"
    assert result.kingdom == "animal"
    assert result.taxon.author == "(Linnaeus, 1758)"
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == [
        "Entomobrya",
        "Entomobryini",
        "Entomobryinae",
        "Entomobryidae",
        "Entomobryoidea",
        "Entomobryomorpha",
        "Collembola",
        "Hexapoda",
        "Arthropoda",
    ]
    assert [r.rank for r in result.ranks][-2:] == ["sous-embranchement", "embranchement"]

    assert result.subtaxa is not None
    assert result.subtaxa.source == "CCW"
    assert [s.name for s in result.subtaxa.items] == ["Entomobrya nivalis f. montana"]

    assert result.synonyms is not None
    assert result.synonyms.source == "CCW"
    assert result.synonyms.items[0].name == "Isotoma nivalis"


@pytest.mark.asyncio
async def test_ccw_synonym_marked_without_following():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Isotoma olivacea"}).respond(
            200, json=_SYNONYM_PAYLOAD
        )
        router.get("https://api.checklistbank.org/dataset/2130/taxon/isotoma-viridis").respond(
            200, json={"link": "https://www.collembola.org/taxa/isotinae.htm"}
        )

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Isotoma olivacea", rank="espèce"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["ccw"]
    assert data["name"] == "Isotoma olivacea"
    assert data["synonym"] is True

    bioref = module.render_bioref(result)
    assert bioref.endswith("<small>(non valide)</small>")


@pytest.mark.asyncio
async def test_ccw_classification_follows_synonym_to_accepted_target():
    accepted_payload = {
        "result": [
            {
                **_ACCEPTED_PAYLOAD["result"][0],
                "id": "isotoma-viridis",
                "usage": {
                    **_ACCEPTED_PAYLOAD["result"][0]["usage"],
                    "link": None,
                    "name": {
                        "scientificName": "Isotoma viridis",
                        "authorship": "Bourlet, 1839",
                        "rank": "species",
                    },
                },
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Isotoma olivacea"}).respond(
            200, json=_SYNONYM_PAYLOAD
        )
        router.get(SEARCH_URL, params={"q": "Isotoma viridis"}).respond(
            200, json=accepted_payload
        )
        router.get(
            "https://api.checklistbank.org/dataset/2130/tree/isotoma-viridis/children"
        ).respond(200, json={"result": [], "last": True})
        router.get(
            "https://api.checklistbank.org/dataset/2130/taxon/isotoma-viridis/synonyms"
        ).respond(200, json={"homotypic": [], "heterotypic": []})

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Isotoma olivacea"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.taxon.name == "Isotoma viridis"
    assert result.kingdom == "animal"
    assert result.classification == "CCW"


@pytest.mark.asyncio
async def test_ccw_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = CcwModule(adapter=ChecklistBankAdapter("2130"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_ccw_render_bioref_absent():
    module = CcwModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_ccw_debug_link_absent():
    module = CcwModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None
