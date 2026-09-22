"""Régression : `_login` (organon/core/mediawiki_bot.py) doit sérialiser deux appels concurrents.
Le garde `if self._logged_in: return` n'est pas atomique — sans verrou, deux coroutines qui
passent toutes deux ce garde avant que la première ne pose `_logged_in = True` déclenchent chacune
leur propre `action=login` sur le même `httpx.AsyncClient`, avec un risque de cookies de session
incohérents."""

import asyncio

import httpx
import pytest
import respx

from organon.core.mediawiki_bot import MediaWikiBotClient

API_URL = "https://example.org/w/api.php"


@pytest.mark.asyncio
async def test_concurrent_login_calls_post_only_once():
    login_calls = 0

    async def handle_token(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        return httpx.Response(200, json={"query": {"tokens": {"logintoken": "tok"}}})

    async def handle_login(request: httpx.Request) -> httpx.Response:
        nonlocal login_calls
        await asyncio.sleep(0)
        login_calls += 1
        return httpx.Response(200, json={"login": {"result": "Success"}})

    with respx.mock(assert_all_called=False) as router:
        router.get(API_URL).mock(side_effect=handle_token)
        router.post(API_URL).mock(side_effect=handle_login)

        client = MediaWikiBotClient(
            api_url=API_URL, username="bot", password="secret", user_agent="organon-test"
        )
        try:
            await asyncio.gather(client._login(), client._login())
        finally:
            await client.aclose()

    assert login_calls == 1, f"attendu 1 POST de login, obtenu {login_calls}"
    assert client._logged_in is True
