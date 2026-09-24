"""Les adaptateurs de sites tiers passent leurs requêtes par un `MinIntervalThrottle`."""

import importlib

import pytest
import respx

from organon.core.auth_settings import get_auth_settings

CASES = [
    ("organon.modules.inpn.adapter", "InpnAdapter", (), "https://taxref.mnhn.fr/", "search", ("x",)),
    (
        "organon.modules.tropicos.adapter",
        "TropicosAdapter",
        (),
        "https://www.tropicos.org/",
        "search",
        ("x",),
    ),
    (
        "organon.modules.algaebase.adapter",
        "AlgaeBaseAdapter",
        (),
        "https://www.algaebase.org/",
        "fetch_key",
        (),
    ),
    (
        "organon.modules.checklistbank",
        "ChecklistBankAdapter",
        ("2018",),
        "https://api.checklistbank.org/",
        "search",
        ("x",),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "cls", "args", "prefix", "method", "margs"), CASES)
async def test_adapter_requests_go_through_throttle(
    monkeypatch, module, cls, args, prefix, method, margs
):
    mod = importlib.import_module(module)
    calls = []

    async def throttle():
        calls.append(1)

    monkeypatch.setattr(mod, "_throttle", throttle)
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith="https://").respond(200, json={})
        async with getattr(mod, cls)(*args) as adapter:
            await getattr(adapter, method)(*margs)
    assert calls


@pytest.mark.asyncio
async def test_tropicos_token_comes_from_settings(monkeypatch):
    from organon.modules.tropicos.adapter import TropicosAdapter

    monkeypatch.setenv("ORGANON_TROPICOS_TOKEN", "jeton-test")
    get_auth_settings.cache_clear()
    try:
        with respx.mock(assert_all_called=False) as router:
            route = router.get(url__startswith="https://www.tropicos.org/").respond(200, json=[])
            async with TropicosAdapter() as adapter:
                await adapter.search("x")
        assert route.calls.last.request.headers["Authorization"] == "Bearer jeton-test"
    finally:
        get_auth_settings.cache_clear()
