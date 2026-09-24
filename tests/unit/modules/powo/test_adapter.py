"""Les échecs réseau de l'adaptateur POWO sont journalisés, jamais muets."""

import pytest
import requests

from organon.modules.powo import adapter as powo_adapter
from organon.modules.powo.adapter import PowoAdapter


@pytest.fixture(autouse=True)
def _failing_get(monkeypatch):
    def boom(path, params):
        raise requests.exceptions.ConnectTimeout("timed out")

    monkeypatch.setattr(powo_adapter, "_get_json", boom)


@pytest.mark.asyncio
async def test_search_failure_returns_empty_and_is_logged(caplog):
    with caplog.at_level("WARNING"):
        assert await PowoAdapter().search("Rosa canina") == []
    assert [r.levelname for r in caplog.records] == ["WARNING"]


@pytest.mark.asyncio
async def test_lookup_failure_returns_none_and_is_logged(caplog):
    with caplog.at_level("WARNING"):
        assert await PowoAdapter().lookup("urn:lsid:ipni.org:names:1") is None
    assert [r.levelname for r in caplog.records] == ["WARNING"]
