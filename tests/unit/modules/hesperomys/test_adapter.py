"""Les échecs réseau et les erreurs GraphQL de l'adaptateur sont journalisés, jamais muets."""

import httpx
import pytest
import respx

from organon.modules.hesperomys.adapter import BASE_URL, HesperomysAdapter


@pytest.mark.asyncio
async def test_network_failure_returns_none_and_is_logged(caplog):
    with respx.mock(assert_all_called=False) as router:
        router.post(BASE_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
        with caplog.at_level("WARNING"):
            result = await HesperomysAdapter()._query("query {}", {})

    assert result is None
    assert [r.levelname for r in caplog.records] == ["WARNING"]


@pytest.mark.asyncio
async def test_graphql_errors_return_none_and_are_logged(caplog):
    with respx.mock(assert_all_called=False) as router:
        router.post(BASE_URL).mock(return_value=httpx.Response(200, json={"errors": [{}]}))
        with caplog.at_level("WARNING"):
            result = await HesperomysAdapter()._query("query {}", {})

    assert result is None
    assert [r.levelname for r in caplog.records] == ["WARNING"]
