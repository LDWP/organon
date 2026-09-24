"""Tests du module COI/IOC (« IOC World Bird List ») : interroge ChecklistBank dataset `2036`
(même schéma de réponse que `col`/`col_xr`/`bryonames`/`wco`, seul le dataset change). Turdus
merula sert de taxon de référence. Contrairement à ces modules, aucun cas de synonyme n'est
exercé ici : vérifié en direct sur l'API (voir `module.py`), ce dataset ne porte que des noms
acceptés (`status` facet = 100% "accepted", `/taxon/<id>/synonyms` toujours vide)."""

import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.coi_ioc.module import CoiIocModule

SEARCH_URL = "https://api.checklistbank.org/dataset/2036/nameusage/search"
CHILDREN_URL = "https://api.checklistbank.org/dataset/2036/tree/Turdus_merula/children"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": "Turdus_merula",
            "classification": [
                {"name": "Neognathae", "rank": "infraclass"},
                {"name": "Passeriformes", "rank": "order"},
                {"name": "Turdidae", "rank": "family"},
                {"name": "Turdus", "rank": "genus", "authorship": "Linnaeus, 1758"},
                {"name": "Turdus merula", "rank": "species", "id": "Turdus_merula"},
            ],
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Turdus merula",
                    "authorship": "Linnaeus, 1758",
                    "rank": "species",
                },
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_coi_ioc_enrichment_only_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Turdus merula"}).respond(200, json=_ACCEPTED_PAYLOAD)

        module = CoiIocModule(adapter=ChecklistBankAdapter("2036"))
        struct = Struct(taxon=TaxonInfo(name="Turdus merula", rank="espèce"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["coi_ioc"]
    assert data["id"] == "Turdus_merula"
    assert data["name"] == "Turdus merula"
    assert data["author"] == "Linnaeus, 1758"
    assert data["rank"] == "espèce"
    assert data["family"] == "Turdidae"
    # Contrat lu par organon.core.selectors.coherence (voir module.py) : toujours "accepté",
    # ce dataset ne portant aucun autre statut.
    assert data["detected_status"] == "accepté"
    # Enrichissement seul : pas d'effet sur la classification.
    assert result.classification == ""
    assert result.ranks == []

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{COI | thrushes | ''Turdus merula'' Linnaeus, 1758 | consulté le="
        + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        "<a href='https://www.checklistbank.org/dataset/2036/taxon/Turdus_merula' "
        "target='_blank' rel='noopener noreferrer'>COI/IOC</a>"
    )


@pytest.mark.asyncio
async def test_coi_ioc_classification_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Turdus merula"}).respond(200, json=_ACCEPTED_PAYLOAD)
        router.get(CHILDREN_URL).respond(
            200,
            json={
                "result": [
                    {
                        "name": "Turdus merula merula",
                        "rank": "subspecies",
                        "authorship": "Linnaeus, 1758",
                        "status": "accepted",
                        "labelHtml": "<i>Turdus merula merula</i> Linnaeus, 1758",
                    },
                    {"name": "Non classé", "rank": "unranked", "status": "accepted"},
                    {"name": "Nom douteux", "rank": "species", "status": "provisional"},
                ],
                "last": True,
            },
        )

        module = CoiIocModule(adapter=ChecklistBankAdapter("2036"))
        struct = Struct(taxon=TaxonInfo(name="Turdus merula"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == "COI"
    assert result.classification_taxobox == "COI"
    assert result.kingdom == "animal"
    assert result.taxon.author == "Linnaeus, 1758"
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == [
        "Turdus",
        "Turdidae",
        "Passeriformes",
        "Neognathae",
        "Aves",
        "Chordata",
    ]
    assert [r.rank for r in result.ranks][-2:] == ["classe", "embranchement"]

    assert result.subtaxa is not None
    assert result.subtaxa.source == "COI"
    assert [s.name for s in result.subtaxa.items] == ["Turdus merula merula"]

    # Aucune résolution/liste de synonymes pour ce dataset accepted-only.
    assert result.synonyms is None


@pytest.mark.asyncio
async def test_coi_ioc_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = CoiIocModule(adapter=ChecklistBankAdapter("2036"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_coi_ioc_render_bioref_family_rank():
    module = CoiIocModule()
    struct = Struct(taxon=TaxonInfo(name="Turdidae", rank="famille"), kingdom="animal")
    struct.links["coi_ioc"] = {
        "id": "fam:Turdidae",
        "name": "Turdidae",
        "author": None,
        "rank": "famille",
        "family": "Turdidae",
    }
    bioref = module.render_bioref(struct)
    assert bioref == "{{COI | thrushes | Turdidae | consulté le=" + bioref.rsplit("=", 1)[1]


def test_coi_ioc_render_bioref_unknown_family():
    # Famille absente de la table IOC : aucun slug valide, donc pas de lien mort.
    module = CoiIocModule()
    struct = Struct(taxon=TaxonInfo(name="Nouvelleidae", rank="famille"), kingdom="animal")
    struct.links["coi_ioc"] = {
        "id": "fam:Nouvelleidae",
        "name": "Nouvelleidae",
        "author": None,
        "rank": "famille",
        "family": "Nouvelleidae",
    }
    assert module.render_bioref(struct) is None


def test_coi_ioc_render_bioref_no_family_ancestor():
    # {{COI}} n'a pas d'usage défini au-dessus du rang famille : pas de citation possible.
    module = CoiIocModule()
    struct = Struct(taxon=TaxonInfo(name="Passeriformes", rank="ordre"), kingdom="animal")
    struct.links["coi_ioc"] = {
        "id": "order:PASSERIFORMES",
        "name": "Passeriformes",
        "author": None,
        "rank": "ordre",
        "family": None,
    }
    assert module.render_bioref(struct) is None


def test_coi_ioc_render_bioref_absent():
    module = CoiIocModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_coi_ioc_debug_link_absent():
    module = CoiIocModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None
