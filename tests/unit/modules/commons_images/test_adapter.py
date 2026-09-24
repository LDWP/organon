"""Régression : une erreur réseau (timeout, connexion refusée...) sur l'un des trois appels de
`CommonsImagesAdapter` ne doit jamais se propager jusqu'à la route `GET /api/v1/commons-images`
(500 brute) — elle doit dégrader vers un résultat vide, au même titre qu'un "non trouvé", comme le
fait déjà le pipeline `/generate` pour ses modules d'enrichissement (voir
`organon.api.routes.generate`)."""

import httpx
import pytest
import respx

from organon.modules.commons_images.adapter import (
    COMMONS_API_URL,
    WIKIDATA_SPARQL_URL,
    CommonsImagesAdapter,
)
from organon.modules.commons_images.service import find_images

CATEGORY_TITLE = "Category:Gadus morhua"


@pytest.mark.asyncio
async def test_category_files_network_timeout_returns_empty():
    with respx.mock(assert_all_called=False) as router:
        router.get(COMMONS_API_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        adapter = CommonsImagesAdapter()
        result = await adapter.category_files(CATEGORY_TITLE)

    assert result == []


@pytest.mark.asyncio
async def test_imageinfo_network_timeout_returns_empty():
    with respx.mock(assert_all_called=False) as router:
        router.get(COMMONS_API_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        adapter = CommonsImagesAdapter()
        result = await adapter.imageinfo(["File:Atlantic cod live.jpg"])

    assert result == {}


@pytest.mark.asyncio
async def test_wikidata_image_network_timeout_returns_none():
    with respx.mock(assert_all_called=False) as router:
        router.get(WIKIDATA_SPARQL_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        adapter = CommonsImagesAdapter()
        result = await adapter.wikidata_image("Gadus morhua")

    assert result is None


@pytest.mark.asyncio
async def test_find_images_degrades_when_wikidata_image_times_out():
    """Reproduit le crash observé en preview : la catégorie Commons et `imageinfo` répondent,
    seul l'appel SPARQL vers Wikidata part en timeout. `find_images` doit tout de même renvoyer
    les suggestions trouvées, simplement sans marquer d'image comme "déjà utilisée sur
    Wikidata"."""
    with respx.mock(assert_all_called=False) as router:
        router.get(COMMONS_API_URL, params={"list": "categorymembers"}).respond(
            200,
            json={
                "query": {
                    "categorymembers": [{"title": "File:Atlantic cod live.jpg"}],
                }
            },
        )
        router.get(COMMONS_API_URL, params={"prop": "imageinfo"}).respond(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Atlantic cod live.jpg",
                            "imageinfo": [
                                {
                                    "thumburl": "https://example/thumb.jpg",
                                    "url": "https://example/full.jpg",
                                    "descriptionurl": "https://example/desc",
                                    "extmetadata": {
                                        "Assessments": {"value": "quality"},
                                        "License": {"value": "cc0"},
                                        "LicenseShortName": {"value": "CC0"},
                                    },
                                }
                            ],
                        }
                    }
                }
            },
        )
        router.get(WIKIDATA_SPARQL_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        adapter = CommonsImagesAdapter()
        result = await find_images("Gadus morhua", adapter)

    assert len(result.suggestions) == 1
    assert result.suggestions[0].file_name == "Atlantic cod live.jpg"
    assert result.suggestions[0].is_wikidata_image is False


@pytest.mark.asyncio
async def test_network_failures_are_logged(caplog):
    with respx.mock(assert_all_called=False) as router:
        router.get(COMMONS_API_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
        router.get(WIKIDATA_SPARQL_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        adapter = CommonsImagesAdapter()
        with caplog.at_level("WARNING"):
            await adapter.category_files(CATEGORY_TITLE)
            await adapter.imageinfo(["File:Atlantic cod live.jpg"])
            await adapter.wikidata_image("Gadus morhua")

    assert [r.levelname for r in caplog.records] == ["WARNING"] * 3
