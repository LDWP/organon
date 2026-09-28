"""POST /api/v1/subtaxa-merge: merge sub-taxa of several sources.

Takes the lists the frontend already holds (see
`GenerateResponse.subtaxa`), and contacts no classification
module.

One exception: when two sources report the same number of species
but differ on some names (synonymy), COL XR is queried per orphan
name (`resolve_col_xr_concept_id`) to check they are the same taxon
before merging; see `reconcile_synonym_groups`. No network call if
the sources agree exactly or their lists differ in size.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from organon.api.deps import require_username
from organon.api.rate_limit import DEFAULT_RATE_LIMIT, limiter
from organon.api.schemas import (
    MergedGroupOut,
    MergedSpeciesOut,
    MergedSubtaxaResponse,
    SubtaxaMergeRequest,
)
from organon.core.rendering.subtaxa_merge import merge_subtaxa, reconcile_synonym_groups
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.lookup import resolve_col_xr_concept_id

router = APIRouter()


@router.post("/subtaxa-merge", response_model=MergedSubtaxaResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def subtaxa_merge(
    request: Request, req: SubtaxaMergeRequest, username: str = Depends(require_username)
) -> MergedSubtaxaResponse:
    """Merge the sub-taxa lists, reconciling synonyms through COL XR."""
    result = merge_subtaxa(
        req.taxon_rank,
        req.taxon_name,
        req.kingdom,
        [(s.module_id, s.subtaxa) for s in req.sources],
    )

    async with ColXrAdapter() as adapter:
        groups = await reconcile_synonym_groups(
            result.groups,
            [s.module_id for s in req.sources],
            lambda name: resolve_col_xr_concept_id(adapter, name, req.kingdom),
        )

    return MergedSubtaxaResponse(
        rank_text=result.rank_text,
        rank_text_singular=result.rank_text_singular,
        pronoun=result.pronoun,
        taxon_phrase=result.taxon_phrase,
        rank_names=result.rank_names,
        groups=[
            MergedGroupOut(
                sources=g.sources,
                kind=g.kind,
                intro=g.intro,
                species=[
                    MergedSpeciesOut(
                        name=s.name, rank=s.rank, line=s.line, default_checked=s.default_checked
                    )
                    for s in g.species
                ],
            )
            for g in groups
        ],
    )
