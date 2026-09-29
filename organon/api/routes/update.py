"""POST /api/v1/update/diagnose and /update/export.

Read-only diagnosis of the gaps between a taxon's Wikidata item and
the Organon sources, then QuickStatements export of the checked
proposals. Never writes to Wikidata.
"""

from __future__ import annotations

from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from organon.api.deps import require_username
from organon.api.rate_limit import limiter
from organon.api.routes.generate import _GENERATE_RATE_LIMIT, _generate_core
from organon.api.schemas import UpdateDiagnoseRequest, UpdateExportRequest, UpdateExportResponse
from organon.core.update_diagnosis import DiagnosticResponse
from organon.modules.wikidata.diagnosis import (
    AmbiguousTaxonError,
    TaxonNotFoundError,
    diagnose_taxon,
)
from organon.modules.wikidata.quickstatements import (
    creation_to_quickstatements,
    to_quickstatements,
)

router = APIRouter()


def _network_error_detail(exc: httpx.HTTPError) -> str:
    """Describe a network error by type and host.

    `str()` of an httpx timeout is empty; the host tells Wikidata from
    a generation source.
    """
    try:
        where = exc.request.url.host
    except RuntimeError:  # exception built without a request
        where = str(exc)
    return f"Requête réseau échouée : {type(exc).__name__} ({where})"


async def _run_diagnosis(
    taxon: str | None,
    qid: str | None,
    classification: str | None,
    domain: str,
    gbif_key: int | None,
) -> DiagnosticResponse:
    """Run the diagnosis, mapping its errors to HTTP statuses."""
    try:
        return await diagnose_taxon(
            taxon=taxon,
            qid=qid,
            classification=classification,
            domain=domain,
            gbif_key=gbif_key,
            generate=_generate_core,
        )
    except TaxonNotFoundError as exc:
        raise HTTPException(404, detail=str(exc) or "Item Wikidata introuvable.") from exc
    except AmbiguousTaxonError as exc:
        raise HTTPException(
            409,
            detail={
                "message": "Plusieurs items Wikidata portent ce nom.",
                "candidates": exc.candidates,
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail=_network_error_detail(exc)) from exc


# Shares the /generate budget: a diagnosis runs a full generation.
@router.post("/update/diagnose", response_model=DiagnosticResponse)
@limiter.shared_limit(_GENERATE_RATE_LIMIT, scope="generate")
async def diagnose(
    request: Request, req: UpdateDiagnoseRequest, username: str = Depends(require_username)
) -> DiagnosticResponse:
    """Return the diagnosis of a taxon."""
    return await _run_diagnosis(req.taxon, req.qid, req.classification, req.domain, req.gbif_key)


@router.post("/update/export", response_model=UpdateExportResponse)
@limiter.shared_limit(_GENERATE_RATE_LIMIT, scope="generate")
async def export(
    request: Request, req: UpdateExportRequest, username: str = Depends(require_username)
) -> UpdateExportResponse:
    """Return the QuickStatements of the checked proposals.

    The diagnosis is recomputed server-side: the client sends only the
    checked ids, never values.
    """
    diagnostic = await _run_diagnosis(
        req.taxon, req.qid, req.classification, req.domain, req.gbif_key
    )
    propositions = {e.proposition.id: e.proposition for e in diagnostic.ecarts if e.proposition}
    creations = {e.creation.id: e.creation for e in diagnostic.ecarts if e.creation}
    unknown = [i for i in req.proposal_ids if i not in propositions and i not in creations]
    if unknown:
        raise HTTPException(422, detail=f"Propositions inconnues du diagnostic : {unknown}")
    ids = list(dict.fromkeys(req.proposal_ids))
    blocks = [creation_to_quickstatements(creations[i]) for i in ids if i in creations]
    chosen = [propositions[i] for i in ids if i in propositions]
    qid = diagnostic.qid or req.qid
    if chosen:
        if not qid:
            raise HTTPException(422, detail="Aucun item Wikidata sur lequel ajouter ces valeurs.")
        blocks.append(to_quickstatements(qid, chosen))
    return UpdateExportResponse(
        quickstatements="\n".join(blocks),
        retrieved=date.today(),
    )
