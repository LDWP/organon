"""Sitelink frwiki de l'item : titre de l'article servant à la comparaison de sa Taxobox."""

from __future__ import annotations

import httpx
import respx

from organon.modules.wikidata.adapter import WIKIDATA_API_URL, WikidataEntityAdapter

# Réponse réelle wbgetentities (Q140, props=claims|labels|sitelinks, sitefilter=frwiki), tronquée.
LION = {
    "entities": {
        "Q140": {
            "id": "Q140",
            "labels": {"fr": {"language": "fr", "value": "lion"}},
            "claims": {},
            "sitelinks": {"frwiki": {"site": "frwiki", "title": "Lion", "badges": ["Q17437796"]}},
        }
    }
}


def test_frwiki_title():
    assert WikidataEntityAdapter().frwiki_title(LION["entities"]["Q140"]) == "Lion"


def test_frwiki_title_absent_without_sitelink():
    assert WikidataEntityAdapter().frwiki_title({"claims": {}}) is None


@respx.mock
async def test_get_entity_requests_the_frwiki_sitelink():
    route = respx.get(WIKIDATA_API_URL).mock(return_value=httpx.Response(200, json=LION))
    entity = await WikidataEntityAdapter().get_entity("Q140")
    params = route.calls.last.request.url.params
    assert "sitelinks" in params["props"].split("|")
    assert params["sitefilter"] == "frwiki"
    assert WikidataEntityAdapter().frwiki_title(entity) == "Lion"


@respx.mock
async def test_get_entities_requests_the_frwiki_sitelink():
    route = respx.get(WIKIDATA_API_URL).mock(return_value=httpx.Response(200, json=LION))
    await WikidataEntityAdapter().get_entities(["Q140"])
    params = route.calls.last.request.url.params
    assert "sitelinks" in params["props"].split("|")
    assert params["sitefilter"] == "frwiki"
