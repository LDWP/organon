"""Tests du module WFO (World Flora Online) contre l'API GraphQL de list.worldfloraonline.org
(voir docstring de `WfoAdapter`), jamais contre le réseau réel. « Quercus robur » (homonymie
Asso 1779 / L. 1753, chaîne réelle vérifiée en direct : espèce -> section -> subgenre -> genre
-> famille -> ordre -> phylum -> sous-règne -> règne -> nœud racine `code`) sert de taxon de
référence."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.wfo.adapter import GRAPHQL_URL, WfoAdapter
from organon.modules.wfo.module import WfoModule
from organon.modules.wfo.ranks import wfo_to_wp_rank


def _name(id_: str, name: str, author: str | None, rank: str, status: str) -> dict:
    return {
        "id": id_,
        "fullNameStringNoAuthorsPlain": name,
        "authorsString": author,
        "rank": rank,
        "role": status,
    }


def _path_entry(name: str, rank: str, author: str | None = None) -> dict:
    has_name = {"fullNameStringNoAuthorsPlain": name, "rank": rank, "authorsString": author}
    return {"hasName": has_name}


SEARCH_QUERCUS_ROBUR = {
    "taxonNameSuggestion": [
        _name("wfo-0000292858", "Quercus robur", "L.", "species", "accepted"),
        _name("wfo-0001275587", "Quercus robur", "Asso", "species", "synonym"),
        _name(
            "wfo-0000292859", "Quercus robur var. acutifolia", "(Bechst.) Asch.", "variety", "synonym"
        ),
    ]
}

# Chaîne réelle (list.worldfloraonline.org, vérifiée en direct) : le taxon lui-même en premier
# élément du chemin (exclu par l'adaptateur), puis ses ancêtres du plus proche au plus lointain,
# jusqu'au nœud technique `code` (pas un vrai rang, filtré par module.py).
ANCESTORS_QUERCUS_ROBUR = {
    "taxonNameById": {
        "currentPreferredUsage": {
            "path": [
                _path_entry("Quercus robur", "species", "L."),
                _path_entry("Quercus sect. Quercus", "section"),
                _path_entry("Quercus subg. Quercus", "subgenus"),
                _path_entry("Quercus", "genus", "L."),
                _path_entry("Fagaceae", "family", "Dumort."),
                _path_entry("Fagales", "order", "Engl."),
                _path_entry("Angiosperms", "phylum"),
                _path_entry("Pteridobiotina", "subkingdom", "Britton & Brown"),
                _path_entry("Plantae", "kingdom", "Haeckel"),
                _path_entry("Code", "code"),
            ]
        }
    }
}


def _respond_by_operation(search_body: dict, ancestors_body: dict):
    def _handler(request):
        payload = request.content.decode()
        if "taxonNameSuggestion" in payload:
            return Response(200, json={"data": search_body})
        return Response(200, json={"data": ancestors_body})

    return _handler


@pytest.mark.asyncio
async def test_wfo_collect_enrichment_mode_prefers_accepted_homonym():
    with respx.mock(assert_all_called=False) as router:
        router.post(GRAPHQL_URL).mock(
            side_effect=_respond_by_operation(SEARCH_QUERCUS_ROBUR, ANCESTORS_QUERCUS_ROBUR)
        )

        module = WfoModule(adapter=WfoAdapter())
        struct = Struct(taxon=TaxonInfo(name="Quercus robur"))
        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["wfo"]["id"] == "wfo-0000292858"
    assert result.links["wfo"]["author"] == "L."
    assert result.kingdom == ""  # pas d'appel ancestors() en mode enrichissement


SEARCH_UNCHECKED = {
    "taxonNameSuggestion": [
        _name("wfo-0001275587", "Quercus robur", "Asso", "species", "synonym"),
    ]
}


@pytest.mark.asyncio
async def test_wfo_collect_classification_not_accepted_returns_none():
    with respx.mock(assert_all_called=False) as router:
        router.post(GRAPHQL_URL).respond(200, json={"data": SEARCH_UNCHECKED})

        module = WfoModule(adapter=WfoAdapter())
        struct = Struct(taxon=TaxonInfo(name="Quercus robur"))
        result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_wfo_collect_classification_builds_ranks_from_exact_api_ranks():
    with respx.mock(assert_all_called=False) as router:
        router.post(GRAPHQL_URL).mock(
            side_effect=_respond_by_operation(SEARCH_QUERCUS_ROBUR, ANCESTORS_QUERCUS_ROBUR)
        )

        module = WfoModule(adapter=WfoAdapter())
        struct = Struct(taxon=TaxonInfo(name="Quercus robur"))
        result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "WFO"
    assert result.classification_taxobox == "WFO"
    assert result.kingdom == "végétal"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "L."

    # ordre du plus proche au plus lointain (déjà cet ordre côté API) ; "code" (racine
    # technique) et "règne" (Plantae, géré séparément via struct.kingdom) exclus. Les rangs
    # infragénériques répétant "Quercus" (section/subgenre) restent distincts par leur rang,
    # impossible à obtenir par une heuristique de suffixe ou de position.
    assert [(r.name, r.rank) for r in result.ranks] == [
        ("Quercus sect. Quercus", "section"),
        ("Quercus subg. Quercus", "sous-genre"),
        ("Quercus", "genre"),
        ("Fagaceae", "famille"),
        ("Fagales", "ordre"),
        ("Angiosperms", "embranchement"),
        ("Pteridobiotina", "sous-règne"),
    ]


def test_wfo_to_wp_rank_maps_enum_and_excludes_technical_nodes():
    assert wfo_to_wp_rank("phylum") == "embranchement"
    assert wfo_to_wp_rank("subkingdom") == "sous-règne"
    assert wfo_to_wp_rank("family") == "famille"
    assert wfo_to_wp_rank("code") is None
    assert wfo_to_wp_rank("unranked") is None
    assert wfo_to_wp_rank(None) is None


@pytest.mark.asyncio
async def test_wfo_adapter_ancestors_excludes_self_and_keeps_api_order():
    with respx.mock(assert_all_called=False) as router:
        router.post(GRAPHQL_URL).respond(200, json={"data": ANCESTORS_QUERCUS_ROBUR})

        chain = await WfoAdapter().ancestors("wfo-0000292858")

    assert [c["nom"] for c in chain] == [
        "Quercus sect. Quercus",
        "Quercus subg. Quercus",
        "Quercus",
        "Fagaceae",
        "Fagales",
        "Angiosperms",
        "Pteridobiotina",
        "Plantae",
        "Code",
    ]


@pytest.mark.asyncio
async def test_wfo_search_graphql_errors_returns_empty():
    with respx.mock(assert_all_called=False) as router:
        router.post(GRAPHQL_URL).respond(
            200, json={"errors": [{"message": "boom"}], "data": None}
        )

        module = WfoModule(adapter=WfoAdapter())
        struct = Struct(taxon=TaxonInfo(name="Zzzznotfoundtaxon12345"))
        result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
