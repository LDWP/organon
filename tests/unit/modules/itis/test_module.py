"""Non-régression : ITIS renvoie parfois plusieurs entrées avec le même `combinedName`
(homonymes stricts). Cas réel observé pour "Aegilops tauschii" : searchByScientificName
renvoie TSN 506695 (author="auct. non Coss.", nom mal appliqué placé en synonyme de "Aegilops
cylindrica") avant TSN 565607 (author="Coss.", le nom valide lui-même). Le module doit retenir
l'homonyme valide, pas le premier arrivé dans la réponse de recherche."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.itis.module import ItisModule


class FakeItisAdapter:
    """Double de `ItisAdapter` : mêmes méthodes async, données figées reproduisant les
    réponses réelles du service ITIS pour ce cas de désambiguïsation."""

    def __init__(self, search_results, accepted_by_tsn):
        self._search_results = search_results
        self._accepted_by_tsn = accepted_by_tsn

    async def search_by_scientific_name(self, name: str) -> list[dict]:
        return self._search_results

    async def accepted_names(self, tsn) -> list[dict]:
        return self._accepted_by_tsn.get(str(tsn), [])

    async def rank_name(self, tsn) -> str | None:
        return "Species"

    async def authorship(self, tsn) -> str | None:
        return "Coss."

    async def full_hierarchy(self, tsn) -> list[dict]:
        return [{"tsn": str(tsn), "author": None, "rankName": "Species", "taxonName": "Aegilops tauschii"}]

    async def hierarchy_down(self, tsn) -> list[dict]:
        return []

    async def synonym_names(self, tsn) -> list[dict]:
        return []

    async def common_names(self, tsn) -> list[dict]:
        return []


AEGILOPS_SEARCH_RESULTS = [
    {
        "tsn": "506695",
        "author": "auct. non Coss.",
        "combinedName": "Aegilops tauschii",
        "kingdom": "Plantae",
    },
    {
        "tsn": "565607",
        "author": "Coss.",
        "combinedName": "Aegilops tauschii",
        "kingdom": "Plantae",
    },
]

AEGILOPS_ACCEPTED_BY_TSN = {
    # Homonyme mal appliqué : redirige vers une autre espèce.
    "506695": [{"acceptedName": "Aegilops cylindrica", "acceptedTsn": "182536"}],
    # Homonyme valide : pas de redirection (getAcceptedNamesFromTSN renvoie acceptedNames nil).
    "565607": [],
}


def _struct(name: str) -> Struct:
    return Struct(taxon=TaxonInfo(name=name))


@pytest.mark.asyncio
async def test_homonym_picks_the_valid_tsn_not_the_first_result():
    adapter = FakeItisAdapter(AEGILOPS_SEARCH_RESULTS, AEGILOPS_ACCEPTED_BY_TSN)
    module = ItisModule(adapter=adapter)
    options = GenerateOptions()

    result = await module.collect(_struct("Aegilops tauschii"), is_classification=True, options=options)

    assert result is not None
    assert result.links["itis"]["id"] == "565607"
    assert "synonym" not in result.links["itis"]
    assert result.taxon.name == "Aegilops tauschii"


@pytest.mark.asyncio
async def test_homonym_enrichment_mode_does_not_flag_the_valid_name_as_synonym():
    adapter = FakeItisAdapter(AEGILOPS_SEARCH_RESULTS, AEGILOPS_ACCEPTED_BY_TSN)
    module = ItisModule(adapter=adapter)
    options = GenerateOptions()

    result = await module.collect(_struct("Aegilops tauschii"), is_classification=False, options=options)

    assert result is not None
    assert result.links["itis"]["id"] == "565607"
    assert "synonym" not in result.links["itis"]


@pytest.mark.asyncio
async def test_ancestor_with_empty_taxon_name_is_skipped_not_fatal():
    """Non-régression : getFullHierarchyFromTSN peut renvoyer un ancêtre avec <taxonName/>
    vide (adapter._text() -> None pour un élément XML vide). Cet ancêtre malformé doit être
    ignoré, pas faire planter toute la classification."""

    search_results = [
        {"tsn": "36485", "author": "L.", "combinedName": "Quercus robur", "kingdom": "Plantae"}
    ]

    class HierarchyWithBlankAncestorAdapter(FakeItisAdapter):
        async def full_hierarchy(self, tsn) -> list[dict]:
            return [
                {"tsn": "999", "author": None, "rankName": "Genus", "taxonName": None},
                {"tsn": str(tsn), "author": None, "rankName": "Species", "taxonName": "Quercus robur"},
            ]

    adapter = HierarchyWithBlankAncestorAdapter(search_results, {"36485": []})
    module = ItisModule(adapter=adapter)

    result = await module.collect(_struct("Quercus robur"), is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.links["itis"]["id"] == "36485"
    assert all(r.nom for r in result.ranks)


@pytest.mark.asyncio
async def test_single_match_is_unaffected_no_extra_lookup():
    """Cas courant (pas d'homonyme) : un seul candidat, pas de désambiguïsation nécessaire."""

    search_results = [
        {"tsn": "36485", "author": "L.", "combinedName": "Quercus robur", "kingdom": "Plantae"}
    ]
    adapter = FakeItisAdapter(search_results, {"36485": []})
    module = ItisModule(adapter=adapter)

    result = await module.collect(_struct("Quercus robur"), is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.links["itis"]["id"] == "36485"


@pytest.mark.asyncio
async def test_vernacular_grouped_by_language():
    class Adapter(FakeItisAdapter):
        async def common_names(self, tsn) -> list[dict]:
            return [
                {"language": "French", "commonName": "Aegilope"},
                {"language": "English", "commonName": "Goatgrass"},
                {"language": "Spanish", "commonName": ""},
                {"language": "Dothraki", "commonName": "qo'"},
            ]

    module = ItisModule(adapter=Adapter(AEGILOPS_SEARCH_RESULTS, AEGILOPS_ACCEPTED_BY_TSN))

    result = await module.collect(
        _struct("Aegilops tauschii"), is_classification=True, options=GenerateOptions()
    )

    assert result.vernacular["ITIS"] == {
        "fr": ["Aegilope"],
        "en": ["Goatgrass"],
        "und": ["qo'"],
    }
