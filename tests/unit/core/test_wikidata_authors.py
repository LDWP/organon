"""Résolution d'abréviations d'auteur botanique via Wikidata (P428)."""

import httpx
import pytest
import respx

from organon.core import wikidata_authors
from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.core.wikidata_authors import WIKIDATA_API, lookup_author_qids, normalize_abbreviation


@pytest.fixture(autouse=True)
def _clean_cache():
    wikidata_authors.clear_cache()


def _hits(*qids: str) -> httpx.Response:
    return httpx.Response(200, json={"query": {"search": [{"title": q} for q in qids]}})


def test_normalize_abbreviation_removes_space_after_dot():
    assert normalize_abbreviation(" H. Klinggr. ") == "H.Klinggr."


@respx.mock
async def test_single_hit_is_resolved_with_normalized_key():
    route = respx.get(WIKIDATA_API).mock(return_value=_hits("Q5933938"))
    assert await lookup_author_qids(["H. Klinggr."]) == {"H.Klinggr.": "Q5933938"}
    assert route.calls.last.request.url.params["srsearch"] == "haswbstatement:P428=H.Klinggr."


@respx.mock
async def test_unknown_and_ambiguous_abbreviations_are_omitted():
    respx.get(WIKIDATA_API).mock(side_effect=[_hits(), _hits("Q1", "Q2")])
    assert await lookup_author_qids(["Zzz.", "Dup."]) == {}


@respx.mock
async def test_results_are_cached_including_negative_ones():
    route = respx.get(WIKIDATA_API).mock(side_effect=[_hits("Q5933938"), _hits()])
    first = await lookup_author_qids(["H.Klinggr.", "Zzz."])
    second = await lookup_author_qids(["H. Klinggr.", "Zzz."])
    assert first == second == {"H.Klinggr.": "Q5933938"}
    assert route.call_count == 2


@respx.mock
async def test_network_error_is_not_cached():
    route = respx.get(WIKIDATA_API).mock(side_effect=[httpx.ConnectError("boom"), _hits("Q1")])
    assert await lookup_author_qids(["A.B."]) == {}
    assert await lookup_author_qids(["A.B."]) == {"A.B.": "Q1"}
    assert route.call_count == 2


@respx.mock
async def test_http_error_status_is_not_cached():
    route = respx.get(WIKIDATA_API).mock(side_effect=[httpx.Response(429), _hits("Q1")])
    assert await lookup_author_qids(["A.B."]) == {}
    assert await lookup_author_qids(["A.B."]) == {"A.B.": "Q1"}
    assert route.call_count == 2


@respx.mock
async def test_client_is_built_by_owned_client_mixin(monkeypatch):
    seen: list[dict] = []
    original = OwnedClientMixin.__init__

    def spy(self, *args, **kwargs):
        seen.append(kwargs)
        original(self, *args, **kwargs)

    monkeypatch.setattr(OwnedClientMixin, "__init__", spy)
    route = respx.get(WIKIDATA_API).mock(return_value=_hits("Q1"))
    await lookup_author_qids(["A.B."])
    assert seen == [{"timeout": 5.0, "headers": {"User-Agent": USER_AGENT}}]
    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT
