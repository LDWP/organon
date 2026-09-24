"""Régression : un vrai 404 (fiche de nomenclature absente) doit toujours renvoyer `None` sans
erreur, mais une panne serveur (503) doit remonter comme exception plutôt que se confondre avec
une citation absente silencieuse (voir `organon.core.http.fetch_text`)."""

import httpx
import pytest
import respx

from organon.modules.taxonomicon.adapter import BASE_URL, TaxonomiconAdapter

TAXON_ID = 42


@pytest.mark.asyncio
async def test_author_citation_404_returns_none():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE_URL}/TaxonName.aspx").respond(404)

        adapter = TaxonomiconAdapter()
        result = await adapter.author_citation(TAXON_ID)

    assert result is None


@pytest.mark.asyncio
async def test_author_citation_server_error_raises():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE_URL}/TaxonName.aspx").respond(503)

        adapter = TaxonomiconAdapter()
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.author_citation(TAXON_ID)
