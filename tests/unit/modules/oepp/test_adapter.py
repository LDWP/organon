"""Régression : un vrai 404 (fiche absente) doit toujours renvoyer les champs vides sans erreur,
mais une panne serveur (503) doit remonter comme exception plutôt que se confondre avec une fiche
vide silencieuse (voir `organon.core.http.fetch_text`)."""

import httpx
import pytest
import respx

from organon.modules.oepp.adapter import BASE_URL, OeppAdapter

EPPO_CODE = "GADEL"


@pytest.mark.asyncio
async def test_taxon_detail_404_returns_empty_fields():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE_URL}/taxon/{EPPO_CODE}").respond(404)

        adapter = OeppAdapter()
        result = await adapter.taxon_detail(EPPO_CODE)

    assert result == {"auteur": None, "vernaculaire_fr": []}


@pytest.mark.asyncio
async def test_taxon_detail_server_error_raises():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE_URL}/taxon/{EPPO_CODE}").respond(503)

        adapter = OeppAdapter()
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.taxon_detail(EPPO_CODE)
