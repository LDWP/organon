"""Tests de l'adaptateur du site FishBase : codes lus sur les pages publiques."""

import httpx
import pytest
import respx

from organon.modules.fishbase import adapter as fishbase_adapter
from organon.modules.fishbase.adapter import FishbaseSiteAdapter

SPECIES_URL = "https://www.fishbase.se/summary/Centrarchus-macropterus.html"
FAMILY_URL = "https://www.fishbase.se/summary/FamilySummary.php"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    async def _instant():
        return None

    monkeypatch.setattr(fishbase_adapter, "_throttle", _instant)


@pytest.mark.asyncio
@respx.mock
async def test_species_code_read_from_page():
    route = respx.get(SPECIES_URL).respond(
        200, text='<a href="/summary/SpeciesSummary.php?id=3363">x</a>'
    )
    assert await FishbaseSiteAdapter().species_code("Centrarchus macropterus") == "3363"
    assert "Organon" in route.calls.last.request.headers["user-agent"]


@pytest.mark.asyncio
@respx.mock
async def test_species_unknown_to_fishbase_is_none():
    # FishBase answers 200 with a generic page for an unknown name.
    respx.get(SPECIES_URL).respond(200, text="<title>FishBase</title>")
    assert await FishbaseSiteAdapter().species_code("Centrarchus macropterus") is None


@pytest.mark.asyncio
@respx.mock
async def test_species_code_rejects_non_binomial_without_request():
    assert await FishbaseSiteAdapter().species_code("Salmo salar trutta") is None
    assert await FishbaseSiteAdapter().species_code("Salmo") is None
    assert not respx.calls


@pytest.mark.asyncio
@respx.mock
async def test_family_code_read_from_page():
    respx.get(FAMILY_URL, params={"family": "Centrarchidae"}).respond(
        200, text='<a href="../identification/SpeciesList.php?famcode=302&areacode=">x</a>'
    )
    assert await FishbaseSiteAdapter().family_code("Centrarchidae") == "302"


@pytest.mark.asyncio
@respx.mock
async def test_server_error_raises():
    respx.get(SPECIES_URL).respond(503)
    with pytest.raises(httpx.HTTPStatusError):
        await FishbaseSiteAdapter().species_code("Centrarchus macropterus")
