"""Lecture du wikitexte d'un article frwiki (base de la comparaison de sa Taxobox)."""

from __future__ import annotations

import httpx
import respx

from organon.modules.wikimedia.wikipedia.adapter import API_URL, WikipediaAdapter


def _response(title: str, content: str) -> dict:
    return {
        "query": {
            "redirects": [{"from": "Panthera leo", "to": title}],
            "pages": [
                {
                    "title": title,
                    "revisions": [
                        {
                            "revid": 232659879,
                            "timestamp": "2025-03-14T09:12:41Z",
                            "slots": {"main": {"content": content}},
                        }
                    ],
                }
            ],
        }
    }


@respx.mock
async def test_wikitext_follows_the_redirect_and_gives_the_resolved_title():
    route = respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=_response("Lion", "{{Taxobox fin}}"))
    )
    page = await WikipediaAdapter().wikitext("Panthera leo")
    assert page is not None
    assert (page.title, page.content) == ("Lion", "{{Taxobox fin}}")
    assert (page.revid, page.timestamp) == (232659879, "2025-03-14T09:12:41Z")
    params = route.calls.last.request.url.params
    assert params["redirects"] == "1"
    assert set(params["rvprop"].split("|")) == {"content", "ids", "timestamp"}


@respx.mock
async def test_wikitext_missing_page():
    respx.get(API_URL).mock(
        return_value=httpx.Response(
            200, json={"query": {"pages": [{"title": "Xyz", "missing": True}]}}
        )
    )
    assert await WikipediaAdapter().wikitext("Xyz") is None


@respx.mock
async def test_portals_unchanged_after_refactor():
    respx.get(API_URL).mock(
        return_value=httpx.Response(
            200, json=_response("Falconidae", "{{Portail|ornithologie|biologie}}")
        )
    )
    assert await WikipediaAdapter().portails("Falconidae") == ["ornithologie", "biologie"]


@respx.mock
async def test_category_exists_queries_the_category_namespace():
    route = respx.get(API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"query": {"pages": {"-1": {"title": "Catégorie:Mecistocephalidae", "missing": ""}}}},
        )
    )
    assert await WikipediaAdapter().category_exists("Mecistocephalidae") is False
    assert route.calls.last.request.url.params["titles"] == "Catégorie:Mecistocephalidae"


@respx.mock
async def test_category_exists_category_present():
    respx.get(API_URL).mock(
        return_value=httpx.Response(
            200, json={"query": {"pages": {"5445339": {"title": "Catégorie:Chilopoda"}}}}
        )
    )
    assert await WikipediaAdapter().category_exists("Chilopoda") is True
