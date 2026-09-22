"""Régression : `fetch_text` doit distinguer une ressource absente (statut dans `empty_statuses`,
ex. 404) d'une panne serveur transitoire (500/503/429...), qui doit lever plutôt que dégrader
silencieusement vers `empty_value` — sinon un module de scraping HTML ne peut jamais signaler
l'erreur à `EnrichmentRunner`."""

import httpx
import pytest
import respx

from organon.core.http import USER_AGENT, OwnedClientMixin, fetch_text

URL = "https://example.test/page"


@pytest.mark.asyncio
async def test_fetch_text_empty_status_returns_empty_value():
    with respx.mock(assert_all_called=False) as router:
        router.get(URL).respond(404)

        async with httpx.AsyncClient() as client:
            result = await fetch_text(client, URL)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_text_server_error_raises():
    with respx.mock(assert_all_called=False) as router:
        router.get(URL).respond(503)

        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_text(client, URL)


@pytest.mark.asyncio
async def test_fetch_text_ok_returns_body():
    with respx.mock(assert_all_called=False) as router:
        router.get(URL).respond(200, text="<html>corps</html>")

        async with httpx.AsyncClient() as client:
            result = await fetch_text(client, URL)

    assert result == "<html>corps</html>"


@pytest.mark.asyncio
async def test_owned_client_sends_organon_user_agent_by_default():
    with respx.mock(assert_all_called=False) as router:
        route = router.get(URL).respond(200)
        async with OwnedClientMixin() as adapter:
            await adapter._client.get(URL)
    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT


@pytest.mark.asyncio
async def test_owned_client_keeps_other_headers_and_allows_ua_override():
    with respx.mock(assert_all_called=False) as router:
        route = router.get(URL).respond(200)
        async with OwnedClientMixin(headers={"Accept": "x/y", "User-Agent": "Autre/1"}) as a:
            await a._client.get(URL)
    headers = route.calls.last.request.headers
    assert headers["Accept"] == "x/y"
    assert headers["User-Agent"] == "Autre/1"


@pytest.mark.asyncio
async def test_owned_client_awaits_throttle_before_each_request():
    calls = []

    async def throttle():
        calls.append(1)

    with respx.mock(assert_all_called=False) as router:
        router.get(URL).respond(200)
        async with OwnedClientMixin(throttle=throttle) as adapter:
            await adapter._client.get(URL)
            await adapter._client.get(URL)
    assert len(calls) == 2
