"""GET /api/v1/sources: every database considered, integrated or not.

Unlike /api/v1/modules, it merges the static inventory with the
live registry, so never-ported databases appear too.
"""

from __future__ import annotations

from fastapi import APIRouter

from organon.api.schemas import SourcesResponse
from organon.core.db_inventory import build_sources_overview
from organon.modules.bootstrap import ensure_modules_registered

router = APIRouter()


@router.get("/sources", response_model=SourcesResponse)
async def list_sources() -> SourcesResponse:
    """Return the merged inventory of sources."""
    ensure_modules_registered()
    return SourcesResponse(**build_sources_overview().model_dump())
