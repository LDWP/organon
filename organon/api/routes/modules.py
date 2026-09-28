"""GET /api/v1/modules: the registered modules and their metadata.

Feeds the "modules to disable" multiselect and the CLI's
`--list-modules`.
"""

from __future__ import annotations

from fastapi import APIRouter

from organon.api.schemas import ModuleInfo
from organon.core.registry import all_modules, default_classification_module
from organon.modules.bootstrap import ensure_modules_registered

router = APIRouter()


@router.get("/modules", response_model=list[ModuleInfo])
async def list_modules() -> list[ModuleInfo]:
    """Return the registered modules, highest priority first."""
    ensure_modules_registered()
    default_id = default_classification_module()
    return [
        ModuleInfo(
            id=m.meta.id,
            can_classify=m.meta.can_classify,
            can_render_external_link=m.meta.can_render_external_link,
            domains=m.meta.domains,
            priority=m.meta.priority,
            is_default=(m.meta.id == default_id),
        )
        for m in sorted(all_modules().values(), key=lambda m: -m.meta.priority)
    ]
