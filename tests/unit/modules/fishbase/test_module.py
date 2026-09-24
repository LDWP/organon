"""Tests du module FishBase : interroge ChecklistBank dataset `1010` (même schéma de réponse
que `col`/`bryonames`, seul le dataset change). Salmo salar (accepté) et Trutta salar (synonyme
homotypique de Salmo salar) servent de taxons de référence — payloads calqués sur des réponses
réelles de l'API (identifiants LSID WoRMS, plateforme Aphia depuis la bascule du 2025-05-01)."""

import httpx
import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.fishbase.module import FishbaseModule

SEARCH_URL = "https://api.checklistbank.org/dataset/1010/nameusage/search"
SALAR_ID = "urn:lsid:marinespecies.org:taxname:127186"
SALMO_ID = "urn:lsid:marinespecies.org:taxname:126141"
SALAR_LINK = "https://www.marinespecies.org/aphia.php?p=taxdetails&id=127186"
CHILDREN_URL = f"https://api.checklistbank.org/dataset/1010/tree/{SALAR_ID}/children"
SYNONYMS_URL = f"https://api.checklistbank.org/dataset/1010/taxon/{SALAR_ID}/synonyms"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": SALAR_ID,
            "classification": [
                {"name": "Osteichthyes", "rank": "parvphylum"},
                {"name": "Actinopterygii", "rank": "gigaclass"},
                {"name": "Actinopteri", "rank": "superclass"},
                {"name": "Teleostei", "rank": "class"},
                {"name": "Salmoniformes", "rank": "order"},
                {"name": "Salmonidae", "rank": "family", "authorship": "Cuvier, 1816"},
                {"name": "Salmo", "rank": "genus", "authorship": "Linnaeus, 1758", "id": SALMO_ID},
                {"name": "Salmo salar", "rank": "species", "id": SALAR_ID},
            ],
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Salmo salar",
                    "authorship": "Linnaeus, 1758",
                    "rank": "species",
                    "link": SALAR_LINK,
                },
            },
        }
    ]
}

_SYNONYM_PAYLOAD = {
    "result": [
        {
            "id": f"{SALAR_ID}-urn:lsid:marinespecies.org:taxname:322192",
            "usage": {
                "status": "synonym",
                "name": {
                    "scientificName": "Trutta salar",
                    "authorship": "(Linnaeus, 1758)",
                    "rank": "species",
                    "link": "https://www.marinespecies.org/aphia.php?p=taxdetails&id=322192",
                },
                "accepted": {"name": {"scientificName": "Salmo salar"}},
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_fishbase_enrichment_only_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Salmo salar"}).respond(200, json=_ACCEPTED_PAYLOAD)

        module = FishbaseModule(adapter=ChecklistBankAdapter("1010"))
        struct = Struct(taxon=TaxonInfo(name="Salmo salar", rank="espèce"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["fishbase"]
    assert data["id"] == SALAR_ID
    assert data["name"] == "Salmo salar"
    assert data["author"] == "Linnaeus, 1758"
    assert data["rank"] == "espèce"
    assert data["link"] == SALAR_LINK
    assert "synonyme" not in data
    # Enrichissement seul : pas d'effet sur la classification.
    assert result.classification == ""
    assert result.ranks == []

    # Espèce : pas de code FishBase numérique côté ChecklistBank (bascule Aphia/WoRMS), repli
    # sur {{Lien web}} vers la fiche WoRMS d'origine plutôt que {{FishBase espèce}}.
    bioref = module.render_bioref(result)
    assert bioref == (
        "{{Lien web | langue=en | titre=''Salmo salar'' Linnaeus, 1758 | "
        f"url={SALAR_LINK} | site=FishBase | consulté le=" + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        f"<a href='{SALAR_LINK}' target='_blank' rel='noopener noreferrer'>FishBase</a>"
    )


@pytest.mark.asyncio
async def test_fishbase_classification_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Salmo salar"}).respond(200, json=_ACCEPTED_PAYLOAD)
        router.get(CHILDREN_URL).respond(
            200,
            json={
                "result": [
                    {
                        "name": "Salmo salar sebago",
                        "rank": "subspecies",
                        "authorship": "Girard, 1853",
                        "status": "accepted",
                        "labelHtml": "<i>Salmo salar sebago</i> Girard, 1853",
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
                "homotypic": [
                    {
                        "name": {
                            "scientificName": "Trutta salar",
                            "authorship": "(Linnaeus, 1758)",
                            "rank": "species",
                        }
                    }
                ],
                "heterotypic": [],
            },
        )

        module = FishbaseModule(adapter=ChecklistBankAdapter("1010"))
        struct = Struct(taxon=TaxonInfo(name="Salmo salar"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == "FishBase"
    assert result.classification_taxobox == "FishBase"
    assert result.kingdom == "animal"
    assert result.taxon.author == "Linnaeus, 1758"
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == [
        "Salmo",
        "Salmonidae",
        "Salmoniformes",
        "Teleostei",
        "Actinopteri",
        "Actinopterygii",
        "Osteichthyes",
    ]
    assert [r.rank for r in result.ranks][:3] == ["genre", "famille", "ordre"]

    assert result.subtaxa is not None
    assert result.subtaxa.source == "FishBase"
    assert [s.name for s in result.subtaxa.items] == ["Salmo salar sebago"]

    assert result.synonyms is not None
    assert result.synonyms.source == "FishBase"
    assert result.synonyms.items[0].name == "Trutta salar"


@pytest.mark.asyncio
async def test_fishbase_synonym_marked_without_following():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Trutta salar"}).respond(200, json=_SYNONYM_PAYLOAD)

        module = FishbaseModule(adapter=ChecklistBankAdapter("1010"))
        struct = Struct(taxon=TaxonInfo(name="Trutta salar", rank="espèce"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["fishbase"]
    assert data["name"] == "Trutta salar"
    assert data["synonym"] is True

    bioref = module.render_bioref(result)
    assert bioref.endswith("<small>(non valide)</small>")


@pytest.mark.asyncio
async def test_fishbase_classification_follows_synonym_to_accepted_target():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Trutta salar"}).respond(200, json=_SYNONYM_PAYLOAD)
        router.get(SEARCH_URL, params={"q": "Salmo salar"}).respond(200, json=_ACCEPTED_PAYLOAD)
        router.get(CHILDREN_URL).respond(200, json={"result": [], "last": True})
        router.get(SYNONYMS_URL).respond(200, json={"homotypic": [], "heterotypic": []})

        module = FishbaseModule(adapter=ChecklistBankAdapter("1010"))
        struct = Struct(taxon=TaxonInfo(name="Trutta salar"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.taxon.name == "Salmo salar"
    assert result.kingdom == "animal"
    assert result.classification == "FishBase"


@pytest.mark.asyncio
async def test_fishbase_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentfishxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = FishbaseModule(adapter=ChecklistBankAdapter("1010"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentfishxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_fishbase_render_bioref_genus():
    module = FishbaseModule()
    struct = Struct(taxon=TaxonInfo(name="Salmo", rank="genre"), kingdom="animal")
    struct.links["fishbase"] = {"id": SALMO_ID, "name": "Salmo", "rank": "genre", "author": None}
    bioref = module.render_bioref(struct)
    assert bioref.startswith("{{FishBase genre | Salmo | consulté le=")
    assert "{{FishBase espèce" not in bioref


def test_fishbase_render_bioref_order():
    module = FishbaseModule()
    struct = Struct(taxon=TaxonInfo(name="Salmoniformes", rank="ordre"), kingdom="animal")
    struct.links["fishbase"] = {
        "id": "urn:lsid:marinespecies.org:taxname:10305",
        "name": "Salmoniformes",
        "rank": "ordre",
        "author": "Cuvier, 1816",
    }
    bioref = module.render_bioref(struct)
    assert bioref.startswith("{{FishBase ordre | Salmoniformes | Cuvier, 1816 | consulté le=")


def test_fishbase_render_bioref_absent():
    module = FishbaseModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_fishbase_debug_link_absent():
    module = FishbaseModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None


_TIMEOUT_SEARCH_RESULT = {
    "result": [
        {
            "id": "urn:lsid:marinespecies.org:taxname:t1",
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Danio rerio",
                    "authorship": "Hamilton, 1822",
                    "rank": "species",
                },
            },
            "classification": [{"id": "fam:1", "name": "Danionidae", "rank": "family"}],
        }
    ]
}
_TAXON_ID = "urn:lsid:marinespecies.org:taxname:t1"


@respx.mock
async def test_fishbase_collect_survives_children_timeout():
    """A timeout on /tree/.../children after a successful search() keeps the base
    classification (name/rank/author); only the subtaxa list stays empty."""
    respx.get("https://api.checklistbank.org/dataset/1010/nameusage/search").mock(
        return_value=httpx.Response(200, json=_TIMEOUT_SEARCH_RESULT)
    )
    respx.get(f"https://api.checklistbank.org/dataset/1010/taxon/urn:lsid:marinespecies.org:taxname:t1/synonyms").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(f"https://api.checklistbank.org/dataset/1010/tree/urn:lsid:marinespecies.org:taxname:t1/children").mock(
        side_effect=httpx.TimeoutException("boom")
    )
    module = FishbaseModule(adapter=ChecklistBankAdapter("1010"))
    struct = Struct(taxon=TaxonInfo(name="Danio rerio"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Danio rerio"
    assert result.taxon.author == "Hamilton, 1822"
    assert result.classification == "FishBase"
    assert result.subtaxa is None
