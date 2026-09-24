"""Tests du module ZooBank : interroge ChecklistBank dataset `2037` (même schéma de réponse que
`col`/`bryonames`, seul le dataset change). Apis mellifera (accepté) sert de taxon de référence,
et vérifie au passage qu'aucun appel réseau supplémentaire n'est fait pour la publication
originale (`accordingTo` déjà présent dans la réponse de recherche)."""

import pytest
import respx

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.checklistbank import ChecklistBankAdapter
from organon.modules.zoobank.module import ZoobankModule

SEARCH_URL = "https://api.checklistbank.org/dataset/2037/nameusage/search"

_APIS_PAYLOAD = {
    "result": [
        {
            "id": "9082c709-6347-4768-a0dc-27dc44400cb2",
            "classification": [
                {"name": "Animalia", "rank": "kingdom"},
                {"name": "Insecta", "rank": "class"},
                {"name": "Hymenoptera", "rank": "order"},
                {"name": "Apis", "rank": "genus"},
                {
                    "name": "Apis mellifera",
                    "rank": "species",
                    "id": "9082c709-6347-4768-a0dc-27dc44400cb2",
                },
            ],
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Apis mellifera",
                    "authorship": "Linnæus, 1758",
                    "rank": "species",
                    "link": "http://zoobank.org/9082c709-6347-4768-a0dc-27dc44400cb2",
                },
                "accordingTo": (
                    "Linnæus, Carolus. 1758. Systema naturae per regna tria naturae, secundum "
                    "classes, ordines, genera, species, cum characteribus, differentiis, "
                    "synonymis, locis. Laurentii Salvii, Holmiae [= Stockholm]. Vol. Tomus I, "
                    "Editio decima, reformata: i-ii, 1-824."
                ),
            },
        }
    ]
}

_SYNONYM_STATUS_PAYLOAD = {
    "result": [
        {
            "id": "42ba03f4-f5d4-4355-8187-204b5601a937",
            "usage": {
                "status": "accepted",  # non fiable comme opinion de synonymie, voir module.py
                "name": {
                    "scientificName": "Bufo vulgaris",
                    "authorship": "Laurenti, 1768",
                    "rank": "species",
                    "link": "http://zoobank.org/42ba03f4-f5d4-4355-8187-204b5601a937",
                },
                "accordingTo": "Laurenti, Joseph N. 1768. Specimen medicum.",
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_zoobank_enrichment_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Apis mellifera"}).respond(200, json=_APIS_PAYLOAD)

        module = ZoobankModule(adapter=ChecklistBankAdapter("2037"))
        struct = Struct(taxon=TaxonInfo(name="Apis mellifera", rank="espèce"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["zoobank"]
    assert data["id"] == "9082c709-6347-4768-a0dc-27dc44400cb2"
    assert data["name"] == "Apis mellifera"
    assert data["author"] == "Linnæus, 1758"
    assert data["rank"] == "espèce"
    assert data["link"] == "http://zoobank.org/9082c709-6347-4768-a0dc-27dc44400cb2"

    assert result.original_publication is not None
    assert "Systema naturae" in result.original_publication

    # Enrichissement seul, jamais une classification.
    assert result.classification == ""
    assert result.ranks == []

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{ZooBank | 9082c709-6347-4768-a0dc-27dc44400cb2 | Apis mellifera | "
        "Linnæus, 1758 | consulté le=" + bioref.rsplit("=", 1)[1]
    )
    assert "''Apis mellifera''" not in bioref  # {{ZooBank}} italicise lui-même le paramètre 2
    assert module.debug_link(result) == (
        "<a href='http://zoobank.org/9082c709-6347-4768-a0dc-27dc44400cb2' "
        "target='_blank' rel='noopener noreferrer'>ZooBank</a>"
    )


@pytest.mark.asyncio
async def test_zoobank_does_not_trust_status_as_classification_signal():
    """Le statut "accepted"/"synonym" de ce dataset ne reflète pas un avis taxonomique
    fiable (voir module.py) : le module ne doit jamais écrire de classification, quel que
    soit ce statut."""
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Bufo vulgaris"}).respond(
            200, json=_SYNONYM_STATUS_PAYLOAD
        )

        module = ZoobankModule(adapter=ChecklistBankAdapter("2037"))
        struct = Struct(taxon=TaxonInfo(name="Bufo vulgaris"), kingdom="animal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == ""
    assert result.ranks == []
    assert result.subtaxa is None
    assert result.synonyms is None


@pytest.mark.asyncio
async def test_zoobank_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = ZoobankModule(adapter=ChecklistBankAdapter("2037"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_zoobank_render_bioref_without_author():
    module = ZoobankModule()
    struct = Struct(
        taxon=TaxonInfo(name="Apis mellifera"),
        links={"zoobank": {"id": "abc123", "name": "Apis mellifera", "author": None}},
    )
    bioref = module.render_bioref(struct)
    assert bioref.startswith("{{ZooBank | abc123 | Apis mellifera | consulté le=")


def test_zoobank_debug_link_none_without_link():
    module = ZoobankModule()
    struct = Struct(
        taxon=TaxonInfo(name="Apis mellifera"),
        links={"zoobank": {"id": "abc123", "name": "Apis mellifera", "author": "L."}},
    )
    assert module.debug_link(struct) is None


def test_zoobank_render_bioref_absent():
    module = ZoobankModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_zoobank_debug_link_absent():
    module = ZoobankModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None


class _DoiChecklistBankAdapter(ChecklistBankAdapter):
    async def resolve_doi_citation(self, doi: str) -> str | None:
        return "{{Article | titre=T}}" if doi == "10.1163/187529275X00239" else None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("according_to", "expected"),
    [
        ("Poinar 1975. https://doi.org/10.1163/187529275X00239", "{{Article | titre=T}}"),
        (
            "Laurenti, Joseph N. 1768. Specimen medicum.",
            "Laurenti, Joseph N. 1768. Specimen medicum.",
        ),
        (
            "Poinar 1975. https://doi.org/10.1234/unknown",
            "Poinar 1975. https://doi.org/10.1234/unknown",
        ),
    ],
)
async def test_zoobank_original_publication_resolves_doi(according_to, expected):
    payload = {
        "result": [
            {
                "id": "x",
                "classification": [],
                "usage": {
                    "status": "accepted",
                    "name": {"scientificName": "Bufo vulgaris", "rank": "species"},
                    "accordingTo": according_to,
                },
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Bufo vulgaris"}).respond(200, json=payload)
        module = ZoobankModule(adapter=_DoiChecklistBankAdapter("2037"))
        struct = Struct(taxon=TaxonInfo(name="Bufo vulgaris"), kingdom="animal")

        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.original_publication == expected
