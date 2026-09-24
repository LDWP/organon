"""Régression : un vrai 404 (taxon absent) doit toujours renvoyer `None` sans erreur, mais une
panne serveur (503) doit remonter comme exception plutôt que se confondre avec un "non trouvé"
silencieux (voir `organon.core.http.fetch_text`)."""

import httpx
import pytest
import respx

from organon.modules.adw.adapter import BASE_URL, AdwAdapter

SLUG = "Sus_scrofa"


@pytest.mark.asyncio
async def test_fetch_404_returns_none():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE_URL}/accounts/{SLUG}/").respond(404)

        adapter = AdwAdapter()
        result = await adapter.fetch(SLUG)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_server_error_raises():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE_URL}/accounts/{SLUG}/").respond(503)

        adapter = AdwAdapter()
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.fetch(SLUG)
