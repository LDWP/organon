"""Tests du module GRIN Taxonomy : interroge ChecklistBank dataset `2018` (même schéma de
réponse que `col`/`bryonames`, seul le dataset change). Zea mays (accepté, avec chaîne
famille→sous-famille→tribu→sous-tribu→genre) et deux synonymes réels (Zea mexicana au rang
espèce, Euchlaena au rang genre) servent de taxons de référence — choisis pour couvrir les deux
branches de `render_bioref` : `{{GRIN espèce}}` (sans paramètre `nv`) contre les cinq autres
modèles (avec `nv`)."""

import httpx
import pytest
import respx
from organon.modules.checklistbank import ChecklistBankAdapter

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.grin.module import GrinModule

SEARCH_URL = "https://api.checklistbank.org/dataset/2018/nameusage/search"
CHILDREN_URL = "https://api.checklistbank.org/dataset/2018/tree/42207/children"
SYNONYMS_URL = "https://api.checklistbank.org/dataset/2018/taxon/42207/synonyms"

_ACCEPTED_PAYLOAD = {
    "result": [
        {
            "id": "42207",
            "classification": [
                {"name": "Poaceae", "rank": "family", "authorship": "Barnhart, nom. cons."},
                {"name": "Panicoideae", "rank": "subfamily"},
                {"name": "Andropogoneae", "rank": "tribe"},
                {"name": "Tripsacinae", "rank": "subtribe"},
                {"name": "Zea", "rank": "genus", "authorship": "L."},
                {"name": "Zea mays", "rank": "species", "id": "42207"},
            ],
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Zea mays",
                    "authorship": "L.",
                    "rank": "species",
                    "link": "https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomydetail?id=42207",
                },
            },
        }
    ]
}

_SPECIES_SYNONYM_PAYLOAD = {
    "result": [
        {
            "id": "103665",
            "usage": {
                "status": "synonym",
                "name": {
                    "scientificName": "Zea mexicana",
                    "authorship": "(Schrad.) Kuntze",
                    "rank": "species",
                    "link": "https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomydetail?id=103665",
                },
                "accepted": {"name": {"scientificName": "Zea mays subsp. mexicana"}},
            },
        }
    ]
}

_GENUS_SYNONYM_PAYLOAD = {
    "result": [
        {
            "id": "gen:14510",
            "usage": {
                "status": "synonym",
                "name": {"scientificName": "Euchlaena", "authorship": "Schrad.", "rank": "genus"},
                "accepted": {"name": {"scientificName": "Zea"}},
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_grin_enrichment_only_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Zea mays"}).respond(200, json=_ACCEPTED_PAYLOAD)

        module = GrinModule(adapter=ChecklistBankAdapter("2018"))
        struct = Struct(taxon=TaxonInfo(name="Zea mays", rank="espèce"), kingdom="végétal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["grin"]
    assert data["id"] == "42207"
    assert data["name"] == "Zea mays"
    assert data["author"] == "L."
    assert data["rank"] == "espèce"
    assert "synonyme" not in data
    # Enrichissement seul : pas d'effet sur la classification.
    assert result.classification == ""
    assert result.ranks == []

    bioref = module.render_bioref(result)
    assert bioref == (
        "{{GRIN espèce | 42207 | ''Zea mays'' L. | consulté le=" + bioref.rsplit("=", 1)[1]
    )
    assert module.debug_link(result) == (
        "<a href='https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomydetail?id=42207' "
        "target='_blank' rel='noopener noreferrer'>GRIN</a>"
    )


@pytest.mark.asyncio
async def test_grin_classification_accepted_species():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Zea mays"}).respond(200, json=_ACCEPTED_PAYLOAD)
        router.get(CHILDREN_URL).respond(
            200,
            json={
                "result": [
                    {
                        "name": "Zea mays subsp. mexicana",
                        "rank": "subspecies",
                        "authorship": "(Schrad.) H. H. Iltis",
                        "status": "accepted",
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
                            "scientificName": "Zea mexicana",
                            "authorship": "(Schrad.) Kuntze",
                            "rank": "species",
                        }
                    }
                ],
            },
        )

        module = GrinModule(adapter=ChecklistBankAdapter("2018"))
        struct = Struct(taxon=TaxonInfo(name="Zea mays"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.classification == "GRIN"
    assert result.classification_taxobox == "GRIN"
    assert result.kingdom == "végétal"
    assert result.taxon.author == "L."
    assert result.taxon.rank == "espèce"
    assert [r.name for r in result.ranks] == [
        "Zea",
        "Tripsacinae",
        "Andropogoneae",
        "Panicoideae",
        "Poaceae",
    ]

    assert result.subtaxa is not None
    assert result.subtaxa.source == "GRIN"
    assert [s.name for s in result.subtaxa.items] == ["Zea mays subsp. mexicana"]

    assert result.synonyms is not None
    assert result.synonyms.source == "GRIN"
    assert result.synonyms.items[0].name == "Zea mexicana"


@pytest.mark.asyncio
async def test_grin_species_synonym_bioref_uses_text_suffix():
    """`{{GRIN espèce}}` n'a pas de paramètre `nv` (vérifié sur son wikicode brut) : un
    synonyme à ce rang retombe sur le suffixe textuel, comme Bryonames."""
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Zea mexicana"}).respond(
            200, json=_SPECIES_SYNONYM_PAYLOAD
        )

        module = GrinModule(adapter=ChecklistBankAdapter("2018"))
        struct = Struct(taxon=TaxonInfo(name="Zea mexicana", rank="espèce"), kingdom="végétal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["grin"]
    assert data["name"] == "Zea mexicana"
    assert data["synonym"] is True

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{GRIN espèce | 103665 | ''Zea mexicana'' (Schrad.) Kuntze |")
    assert "nv" not in bioref
    assert bioref.endswith("<small>(non valide)</small>")


@pytest.mark.asyncio
async def test_grin_genus_synonym_bioref_uses_nv_param():
    """Contrairement à l'espèce, `{{GRIN genre}}` porte un paramètre `nv` positionnel natif —
    utilisé ici plutôt que le suffixe textuel."""
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Euchlaena"}).respond(
            200, json=_GENUS_SYNONYM_PAYLOAD
        )

        module = GrinModule(adapter=ChecklistBankAdapter("2018"))
        struct = Struct(taxon=TaxonInfo(name="Euchlaena", rank="genre"), kingdom="végétal")
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is not None
    data = result.links["grin"]
    assert data["id"] == "gen:14510"
    assert data["synonym"] is True

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{GRIN genre | 14510 | ''Euchlaena'' Schrad. | nv | consulté le=")
    assert not bioref.endswith("<small>(non valide)</small>")

    assert module.debug_link(result) == (
        "<a href='https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomygenus.aspx?id=14510' "
        "target='_blank' rel='noopener noreferrer'>GRIN</a>"
    )


@pytest.mark.asyncio
async def test_grin_classification_follows_synonym_to_accepted_target():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Euchlaena"}).respond(
            200, json=_GENUS_SYNONYM_PAYLOAD
        )
        router.get(SEARCH_URL, params={"q": "Zea"}).respond(
            200,
            json={
                "result": [
                    {
                        "id": "gen:13020",
                        "classification": [{"name": "Zea", "rank": "genus", "id": "gen:13020"}],
                        "usage": {
                            "status": "accepted",
                            "name": {"scientificName": "Zea", "authorship": "L.", "rank": "genus"},
                        },
                    }
                ]
            },
        )
        router.get("https://api.checklistbank.org/dataset/2018/tree/gen:13020/children").respond(
            200, json={"result": [], "last": True}
        )
        router.get("https://api.checklistbank.org/dataset/2018/taxon/gen:13020/synonyms").respond(
            200, json={"homotypic": [], "heterotypic": []}
        )

        module = GrinModule(adapter=ChecklistBankAdapter("2018"))
        struct = Struct(taxon=TaxonInfo(name="Euchlaena"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=True, options=options)

    assert result is not None
    assert result.taxon.name == "Zea"
    assert result.kingdom == "végétal"
    assert result.classification == "GRIN"


@pytest.mark.asyncio
async def test_grin_not_found():
    with respx.mock(assert_all_called=False) as router:
        router.get(SEARCH_URL, params={"q": "Nonexistentgenusxyz zzz"}).respond(
            200, json={"result": []}
        )

        module = GrinModule(adapter=ChecklistBankAdapter("2018"))
        struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))
        options = GenerateOptions()

        result = await module.collect(struct, is_classification=False, options=options)

    assert result is None


def test_grin_render_bioref_absent():
    module = GrinModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_grin_debug_link_absent():
    module = GrinModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.debug_link(struct) is None


_TIMEOUT_SEARCH_RESULT = {
    "result": [
        {
            "id": "gen:1",
            "usage": {
                "status": "accepted",
                "name": {
                    "scientificName": "Zea mays",
                    "authorship": "L.",
                    "rank": "species",
                },
            },
            "classification": [{"id": "fam:1", "name": "Poaceae", "rank": "family"}],
        }
    ]
}


@respx.mock
async def test_grin_collect_survives_synonyms_timeout():
    """A timeout on /synonyms after a successful search() keeps the base classification
    (name/rank/author) already written to `struct`."""
    respx.get("https://api.checklistbank.org/dataset/2018/nameusage/search").mock(
        return_value=httpx.Response(200, json=_TIMEOUT_SEARCH_RESULT)
    )
    respx.get(f"https://api.checklistbank.org/dataset/2018/tree/gen:1/children").mock(
        return_value=httpx.Response(200, json={"result": [], "last": True})
    )
    respx.get(f"https://api.checklistbank.org/dataset/2018/taxon/gen:1/synonyms").mock(
        side_effect=httpx.TimeoutException("boom")
    )
    module = GrinModule(adapter=ChecklistBankAdapter("2018"))
    struct = Struct(taxon=TaxonInfo(name="Zea mays"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.name == "Zea mays"
    assert result.taxon.author == "L."
    assert result.classification == "GRIN"
    assert result.synonyms is None
