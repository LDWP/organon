"""Tests du module Bryonames : interroge ChecklistBank dataset `170394` (même schéma de réponse
que `col`/`col_xr`, seul le dataset change). Sphagnum palustre (accepté) et Isocladus (synonyme
hétérotypique de Sphagnum) servent de taxons de référence."""

import httpx
import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.bryonames.module import BryonamesModule

SEARCH_URL = "https://api.checklistbank.org/dataset/170394/nameusage/search"
CHILDREN_URL = "https://api.checklistbank.org/dataset/170394/tree/28565141/children"
SYNONYMS_URL = "https://api.checklistbank.org/dataset/170394/taxon/28565141/synonyms"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": "28565141",
            "classification": [
                {"name": "Bryobiotina", "rank": "subkingdom"},
                {"name": "Bryophyta", "rank": "phylum", "authorship": "Schimp."},
                {"name": "Sphagnopsida", "rank": "class", "authorship": "Schimp."},
                {"name": "Sphagnales", "rank": "order", "authorship": "Limpr."},
                {"name": "Sphagnaceae", "rank": "family", "authorship": "Dumort."},
                {"name": "Sphagnum", "rank": "genus", "authorship": "L."},
                {"name": "Sphagnum palustre", "rank": "species", "id": "28565141"},
            ],
            "usage": {
                "status": "accepted",
                "extinct": False,
                "name": {
                    "scientificName": "Sphagnum palustre",
                    "authorship": "L.",
                    "rank": "species",
                    "link": "https://www.tropicos.org/name/35001500",
                },
            },
        }
    ]
}

_SYNONYM_PAYLOAD = {
    "result": [
        {
            "id": "28507230",
            "usage": {
                "status": "synonym",
                "name": {
                    "scientificName": "Isocladus",
                    "authorship": "Lindb.",
                    "rank": "genus",
                    "link": "https://www.tropicos.org/name/35000652",
                },
                "accepted": {"name": {"scientificName": "Sphagnum"}},
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_bryonames_enrichment_only_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Sphagnum palustre"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )

        module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
        struct = Struct(taxon=TaxonInfo(name="Sphagnum palustre", rank="espèce"), kingdom="végétal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["bryonames"]
    assert data["id"] == "28565141"
    assert data["name"] == "Sphagnum palustre"
    assert data["author"] == "L."
    assert data["rank"] == "espèce"
    assert "synonyme" not in data
    # Enrichissement seul : pas d'effet sur la classification.
    assert result.classification == ""
    assert result.ranks == []

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{Lien web | langue=en | titre=''Sphagnum palustre'' L. | "
        "url=https://www.bryonames.org/nomenclator?group=Sphagnum%20palustre | site=Bryonames | consulté le="
        + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        "<a href='https://www.bryonames.org/nomenclator?group=Sphagnum%20palustre' "
        "target='_blank' rel='noopener noreferrer'>Bryonames</a>"
    )


@pytest.mark.asyncio
async def test_bryonames_link_family_uses_nomenclator_not_tropicos():
    payload = {
        "result": [
            {
                "id": "1",
                "usage": {
                    "status": "accepted",
                    "name": {
                        "scientificName": "Blasiaceae",
                        "authorship": "H.Klinggr.",
                        "rank": "family",
                        "link": "https://www.tropicos.org/name/35002602",
                    },
                },
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Blasiaceae"}).respond(200, json=payload)
        module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
        struct = Struct(taxon=TaxonInfo(name="Blasiaceae", rank="famille"), kingdom="végétal")
        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    url = "https://www.bryonames.org/nomenclator?group=Blasiaceae"
    assert f"url={url} " in module.render_bioref(result)
    assert f"<a href='{url}'" in module.debug_link(result)
    assert "tropicos" not in module.render_bioref(result)


@pytest.mark.asyncio
async def test_bryonames_classification_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Sphagnum palustre"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )
        router.get(CHILDREN_URL).respond(
            200,
            json={
                "result": [
                    {
                        "name": "Sphagnum palustre var. centrale",
                        "rank": "variety",
                        "authorship": "Warnst.",
                        "status": "accepted",
                        "labelHtml": "<i>Sphagnum palustre var. centrale</i> Warnst.",
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
                            "scientificName": "Sphagnum palustre var. compactum",
                            "authorship": "Schimp.",
                            "rank": "variety",
                        }
                    }
                ],
            },
        )

        module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
        struct = Struct(taxon=TaxonInfo(name="Sphagnum palustre"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == "Bryonames"
    assert result.classification_taxobox == "Bryonames"
    assert result.kingdom == "végétal"
    assert result.taxon.author == "L."
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == [
        "Sphagnum",
        "Sphagnaceae",
        "Sphagnales",
        "Sphagnopsida",
        "Bryophyta",
        "Bryobiotina",
    ]

    assert result.subtaxa is not None
    assert result.subtaxa.source == "Bryonames"
    assert [s.name for s in result.subtaxa.items] == ["Sphagnum palustre var. centrale"]

    assert result.synonyms is not None
    assert result.synonyms.source == "Bryonames"
    assert result.synonyms.items[0].name == "Sphagnum palustre var. compactum"


@pytest.mark.asyncio
async def test_bryonames_synonym_marked_without_following():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Isocladus"}).respond(200, json=_SYNONYM_PAYLOAD)

        module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
        struct = Struct(taxon=TaxonInfo(name="Isocladus", rank="genre"), kingdom="végétal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["bryonames"]
    assert data["name"] == "Isocladus"
    assert data["synonym"] is True

    bioref = module.render_bioref(result)
    assert bioref.endswith("<small>(non valide)</small>")


@pytest.mark.asyncio
async def test_bryonames_classification_follows_synonym_to_accepted_target():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Isocladus"}).respond(200, json=_SYNONYM_PAYLOAD)
        router.get(SEARCH_URL, params={"q": "Sphagnum"}).respond(
            200,
            json={
                "result": [
                    {
                        "id": "28562402",
                        "classification": [{"name": "Sphagnum", "rank": "genus", "id": "28562402"}],
                        "usage": {
                            "status": "accepted",
                            "name": {"scientificName": "Sphagnum", "authorship": "L.", "rank": "genus"},
                        },
                    }
                ]
            },
        )
        router.get("https://api.checklistbank.org/dataset/170394/tree/28562402/children").respond(
            200, json={"result": [], "last": True}
        )
        router.get("https://api.checklistbank.org/dataset/170394/taxon/28562402/synonyms").respond(
            200, json={"homotypic": [], "heterotypic": []}
        )

        module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
        struct = Struct(taxon=TaxonInfo(name="Isocladus"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.taxon.name == "Sphagnum"
    assert result.kingdom == "végétal"
    assert result.classification == "Bryonames"


@pytest.mark.asyncio
async def test_bryonames_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_bryonames_render_bioref_absent():
    module = BryonamesModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_bryonames_debug_link_absent():
    module = BryonamesModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None


_TIMEOUT_SEARCH_RESULT = {
    "result": [
        {
            "id": "t1",
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Sphagnum palustre",
                    "authorship": "L.",
                    "rank": "species",
                },
            },
            "classification": [{"id": "k1", "name": "Sphagnaceae", "rank": "family"}],
        }
    ]
}


@respx.mock
async def test_bryonames_collect_survives_synonyms_timeout():
    """A timeout on /synonyms after a successful search() keeps the base classification
    (name/rank/author) already written to `struct`."""
    respx.get("https://api.checklistbank.org/dataset/170394/nameusage/search").mock(
        return_value=httpx.Response(200, json=_TIMEOUT_SEARCH_RESULT)
    )
    respx.get(f"https://api.checklistbank.org/dataset/170394/tree/t1/children").mock(
        return_value=httpx.Response(200, json={"result": [], "last": True})
    )
    respx.get(f"https://api.checklistbank.org/dataset/170394/taxon/t1/synonyms").mock(
        side_effect=httpx.TimeoutException("boom")
    )
    module = BryonamesModule(adapter=ChecklistBankAdapter("170394"))
    struct = Struct(taxon=TaxonInfo(name="Sphagnum palustre"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Sphagnum palustre"
    assert result.taxon.author == "L."
    assert result.classification == "Bryonames"
    assert result.synonyms is None
