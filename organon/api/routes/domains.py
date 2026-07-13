"""GET /api/v1/domains — expose l'arbre de domaines réel (règne + sous-groupes) pour peupler
dynamiquement le sélecteur de domaine de l'interface."""

from __future__ import annotations

from fastapi import APIRouter

from organon.api.schemas import DomainInfo
from organon.core.domains import DOMAINES_TRUE, DomainTree

router = APIRouter()


def _flatten(tree: DomainTree, parent: str | None, out: list[DomainInfo]) -> None:
    for name, node in tree.items():
        out.append(DomainInfo(id=name, parent=parent))
        _flatten(node.sous, name, out)


@router.get("/domains", response_model=list[DomainInfo])
async def list_domains() -> list[DomainInfo]:
    out: list[DomainInfo] = [DomainInfo(id="*", parent=None)]
    _flatten(DOMAINES_TRUE, None, out)
    return out
