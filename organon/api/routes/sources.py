"""GET /api/v1/sources — vue d'ensemble de toutes les bases de données considérées pour le
projet, intégrées ou non, pour la page « Sources » du frontend. Contrairement à
/api/v1/modules (qui ne liste que les modules réellement enregistrés), cette route couvre
aussi les bases jamais portées, en fusionnant l'inventaire statique
(organon/core/data/db_inventory.yaml) avec l'état réel du registre."""

from __future__ import annotations

from fastapi import APIRouter

from organon.api.schemas import SourcesResponse
from organon.core.db_inventory import build_sources_overview
from organon.modules.bootstrap import ensure_modules_registered

router = APIRouter()


@router.get("/sources", response_model=SourcesResponse)
async def list_sources() -> SourcesResponse:
    ensure_modules_registered()
    return build_sources_overview()
