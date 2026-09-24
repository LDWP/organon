import httpx
import pytest
import respx

from organon.modules.reptile_database.adapter import BASE_URL, ReptileDatabaseAdapter

SEARCH = f"{BASE_URL}/advanced_search"
FORM_ONLY = "<html><h1>Advanced search</h1></html>"
NO_SPECIES = "<html><h1>Search results</h1><p>No species were found.</p></html>"
RESULTS = "<html><h1>Search results</h1><table><tr><td>Varanus varius</td></tr></table></html>"


@pytest.mark.parametrize(
    ("page", "expected"),
    [(RESULTS, True), (NO_SPECIES, False), (FORM_ONLY, False)],
    ids=["found", "no_species", "bare_form"],
)
@respx.mock
async def test_genus_exists(page, expected):
    respx.get(SEARCH).mock(return_value=httpx.Response(200, text=page))
    async with ReptileDatabaseAdapter() as adapter:
        assert await adapter.genus_exists("Varanus") is expected


@respx.mock
async def test_search_uses_the_params_the_site_redirects_to():
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, text=RESULTS))
    async with ReptileDatabaseAdapter() as adapter:
        await adapter.family_exists("Varanidae")
    params = route.calls.last.request.url.params
    assert params["taxon"] == "Varanidae"
    assert params["exact[0]"] == "taxon"
    assert params["submit"] == "Search"
    assert "do" not in params
