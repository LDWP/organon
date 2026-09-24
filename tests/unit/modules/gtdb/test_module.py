"""Tests du module GTDB : interroge ChecklistBank dataset `2214` (même schéma de réponse que
`col`/`bryonames`, seul le dataset change). *Escherichia coli* (nom binomial classique) et
*Escherichia hormaechei_A* (placeholder GTDB pour un génome non cultivé, vérifié en direct) servent
de taxons de référence — le second documente pourquoi ce module reste `can_classify=False`."""

import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.gtdb.module import GtdbModule

SEARCH_URL = "https://api.checklistbank.org/dataset/2214/nameusage/search"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": "s__Escherichia coli",
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Escherichia coli",
                    "rank": "species",
                    "link": "https://gtdb.ecogenomic.org/tree?r=s__Escherichia%20coli",
                },
            },
        }
    ]
}

_PLACEHOLDER_PAYLOAD = {
    "result": [
        {
            "id": "s__Escherichia hormaechei_A",
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Escherichia hormaechei_A",
                    "rank": "species",
                    "link": "https://gtdb.ecogenomic.org/tree?r=s__Escherichia%20hormaechei_A",
                },
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_gtdb_enrichment_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Escherichia coli"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )

        module = GtdbModule(adapter=ChecklistBankAdapter("2214"))
        struct = Struct(taxon=TaxonInfo(name="Escherichia coli", rank="espèce"), kingdom="bactérie")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["gtdb"]
    assert data["id"] == "s__Escherichia coli"
    assert data["name"] == "Escherichia coli"
    assert data["rank"] == "espèce"
    assert data["link"] == "https://gtdb.ecogenomic.org/tree?r=s__Escherichia%20coli"

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{Lien web | langue=en | titre=''Escherichia coli'' | "
        "url=https://gtdb.ecogenomic.org/tree?r=s__Escherichia%20coli | site=GTDB | consulté le="
        + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        "<a href='https://gtdb.ecogenomic.org/tree?r=s__Escherichia%20coli' "
        "target='_blank' rel='noopener noreferrer'>GTDB</a>"
    )


@pytest.mark.asyncio
async def test_gtdb_never_writes_classification_even_when_requested():
    """`is_classification=True` ne doit avoir aucun effet : GTDB est enrichissement seul
    (`can_classify=False`), jamais une source de hiérarchie concurrente de LPSN — voir le
    docstring de tête de `organon.modules.gtdb.module`."""
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Escherichia coli"}).respond(
            200, json=_ACCEPTED_PAYLOAD
        )

        module = GtdbModule(adapter=ChecklistBankAdapter("2214"))
        struct = Struct(taxon=TaxonInfo(name="Escherichia coli"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == ""
    assert result.ranks == []
    assert result.taxon.name == "Escherichia coli"


@pytest.mark.asyncio
async def test_gtdb_surfaces_placeholder_name_as_enrichment_only():
    """Un enregistrement à suffixe GTDB (génome non cultivé sans nom latin publié) est cité tel
    quel dans le lien externe — factuellement ce que GTDB appelle ce taxon — sans jamais pouvoir
    contaminer `struct.taxon.name`/`struct.classification`."""
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Escherichia hormaechei_A"}).respond(
            200, json=_PLACEHOLDER_PAYLOAD
        )

        module = GtdbModule(adapter=ChecklistBankAdapter("2214"))
        struct = Struct(taxon=TaxonInfo(name="Escherichia hormaechei_A"), kingdom="bactérie")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.links["gtdb"]["name"] == "Escherichia hormaechei_A"
    assert result.classification == ""


@pytest.mark.asyncio
async def test_gtdb_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = GtdbModule(adapter=ChecklistBankAdapter("2214"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_gtdb_render_bioref_absent():
    module = GtdbModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_gtdb_debug_link_absent():
    module = GtdbModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None


def test_gtdb_no_checklistbank_fallback_without_link():
    module = GtdbModule()
    struct = Struct(
        taxon=TaxonInfo(name="Escherichia coli"),
        links={"gtdb": {"id": "s__Escherichia coli", "name": "Escherichia coli", "author": None}},
    )
    assert module.render_bioref(struct) is None
    assert module.debug_link(struct) is None
