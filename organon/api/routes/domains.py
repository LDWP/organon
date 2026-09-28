"""GET /api/v1/domains: the domain tree, for the domain selector."""

from __future__ import annotations

from fastapi import APIRouter

from organon.api.schemas import DomainInfo
from organon.core.domains import ALL_ACCEPTED_TREE, DomainTree

router = APIRouter()


def _flatten(tree: DomainTree, parent: str | None, out: list[DomainInfo]) -> None:
    for name, node in tree.items():
        out.append(DomainInfo(id=name, parent=parent))
        _flatten(node.children, name, out)


@router.get("/domains", response_model=list[DomainInfo])
async def list_domains() -> list[DomainInfo]:
    """Return the flattened domain tree."""
    out: list[DomainInfo] = [DomainInfo(id="*", parent=None)]
    _flatten(ALL_ACCEPTED_TREE, None, out)
    return out
