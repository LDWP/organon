"""GET /api/v1/commons-images: Commons image suggestions.

Selection is described in `organon.modules.commons_images.service`.
Read-only and anonymous: browsing suggestions edits nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from organon.api.deps import require_username
from organon.api.rate_limit import DEFAULT_RATE_LIMIT, limiter
from organon.api.schemas import CommonsImagesResponse, CommonsImageSuggestion
from organon.modules.commons_images.adapter import CommonsImagesAdapter
from organon.modules.commons_images.service import find_images

router = APIRouter()


@router.get("/commons-images", response_model=CommonsImagesResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def commons_images(
    request: Request,
    taxon: str = Query(..., min_length=1),
    username: str = Depends(require_username),
) -> CommonsImagesResponse:
    """Return Commons image suggestions for the taxobox of `taxon`."""
    async with CommonsImagesAdapter() as adapter:
        result = await find_images(taxon, adapter)

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
