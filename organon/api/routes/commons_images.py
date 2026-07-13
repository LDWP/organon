"""GET /api/v1/commons-images — suggestions d'images Wikimedia Commons pour la taxobox d'un
taxon (voir `organon.modules.commons_images.service` pour la sélection : catégorie du taxon +
distinction qualité/featured + licence permissive + dédoublonnage avec l'image Wikidata P18).

Lecture seule et anonyme (pas d'appel à `require_username`, contrairement à
`organon.api.routes.taxobox_refresh`) : parcourir des suggestions d'images n'édite rien, seul le
choix final laissé à l'utilisateur applique un changement, et seulement dans le wikitexte déjà en
sa possession côté frontend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from organon.api.schemas import CommonsImagesResponse, CommonsImageSuggestion
from organon.modules.commons_images.adapter import CommonsImagesAdapter
from organon.modules.commons_images.service import find_images

router = APIRouter()


@router.get("/commons-images", response_model=CommonsImagesResponse)
async def commons_images(taxon: str = Query(..., min_length=1)) -> CommonsImagesResponse:
    adapter = CommonsImagesAdapter()
    try:
        result = await find_images(taxon, adapter)
    finally:
        await adapter.aclose()

    return CommonsImagesResponse(
        taxon=result.taxon,
        category_title=result.category_title,
        search_url=result.search_url,
        category_url=result.category_url,
        suggestions=[
            CommonsImageSuggestion(
                file_name=s.file_name,
                thumb_url=s.thumb_url,
                page_url=s.page_url,
                license_code=s.license_code,
                license_label=s.license_label,
                assessments=s.assessments,
                is_wikidata_image=s.is_wikidata_image,
            )
            for s in result.suggestions
        ],
    )
