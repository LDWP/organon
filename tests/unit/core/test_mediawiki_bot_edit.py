from urllib.parse import parse_qs

import httpx
import pytest
import respx

from organon.core.mediawiki_bot import (
    BotEditConflictError,
    BotEditError,
    BotMaxLagError,
    MediaWikiBotClient,
)

API_URL = "https://example.org/w/api.php"


def _client(reponse_edit, posts):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            tokens = {"logintoken": "l", "csrftoken": "c"}
            return httpx.Response(200, json={"query": {"tokens": tokens}})
        data = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        posts.append(data)
        if data["action"] == "login":
            return httpx.Response(200, json={"login": {"result": "Success"}})
        return reponse_edit

    router = respx.mock(assert_all_called=False)
    router.route(url=API_URL).mock(side_effect=handler)
    return router, MediaWikiBotClient(
        api_url=API_URL, username="Bot", password="x", user_agent="test"
    )


async def test_edition_transmet_baserevid_basetimestamp_nocreate_bot():
    posts: list[dict] = []
    ok = httpx.Response(200, json={"edit": {"result": "Success", "newrevid": 5}})
    router, client = _client(ok, posts)
    with router:
        await client.edit_page(
            title="Foo",
            text="t",
            summary="s",
            baserevid=10,
            basetimestamp="2026-10-03T10:00:00Z",
            nocreate=True,
            bot=True,
        )
    edit = posts[-1]
    assert (edit["baserevid"], edit["nocreate"], edit["bot"]) == ("10", "1", "1")
    assert edit["basetimestamp"] == "2026-10-03T10:00:00Z"


async def test_edition_sans_options_nenvoie_aucun_champ_supplementaire():
    posts: list[dict] = []
    router, client = _client(httpx.Response(200, json={"edit": {"result": "Success"}}), posts)
    with router:
        await client.edit_page(title="Foo", text="t", summary="s")
    assert not {"baserevid", "basetimestamp", "nocreate", "bot"} & posts[-1].keys()


async def test_conflit_deedition_leve_botEditConflict():
    router, client = _client(
        httpx.Response(200, json={"error": {"code": "editconflict", "info": "x"}}), []
    )
    with router, pytest.raises(BotEditConflictError):
        await client.edit_page(title="Foo", text="t", summary="s", baserevid=1)


async def test_maxlag_leve_botMaxLag_avec_retry_after():
    reponse = httpx.Response(
        200, json={"error": {"code": "maxlag", "info": "x"}}, headers={"Retry-After": "7"}
    )
    router, client = _client(reponse, [])
    with router, pytest.raises(BotMaxLagError) as exc:
        await client.edit_page(title="Foo", text="t", summary="s")
    assert exc.value.retry_after == 7.0


async def test_autre_erreur_reste_botEditError():
    router, client = _client(
        httpx.Response(200, json={"error": {"code": "protectedpage", "info": "x"}}), []
    )
    with router, pytest.raises(BotEditError) as exc:
        await client.edit_page(title="Foo", text="t", summary="s")
    assert not isinstance(exc.value, (BotEditConflictError, BotMaxLagError))


async def test_edition_exige_une_session_connectee():
    posts: list[dict] = []
    router, client = _client(httpx.Response(200, json={"edit": {"result": "Success"}}), posts)
    with router:
        await client.edit_page(title="Foo", text="t", summary="s")
    assert posts[-1]["assert"] == "user"
