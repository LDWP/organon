"""POST /api/v1/subtaxa-merge — fusionne les sous-taxons de plusieurs sources de classification
déjà résolues côté frontend (voir `organon.core.rendering.subtaxa_merge`), pour le mode de rendu
"sous-taxons fusionnés" de l'onglet Wikitexte. Prend en entrée les listes déjà récupérées par le
frontend (`resultsBySource`, voir `GenerateResponse.subtaxa_liste`), ne recontacte aucun module de
classification.

Exception ciblée : quand deux sources rapportent le même nombre d'espèces mais divergent sur un ou
plusieurs noms (synonymie, voir Discussion Projet:Biologie/Organon #30), un appel réseau COL XR
est fait par nom orphelin (`resolve_col_xr_concept_id`, qui suit la redirection vers le concept
accepté même si le nom orphelin n'est lui-même qu'un synonyme dans COL XR) pour vérifier s'il
s'agit du même taxon avant de fusionner (voir
`organon.core.rendering.subtaxa_merge.reconcile_synonym_groups`). Aucun appel réseau si toutes les
sources s'accordent déjà exactement, ou si leurs listes divergentes ont des tailles différentes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from organon.api.rate_limit import limiter
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
@limiter.limit("30/minute")
async def subtaxa_merge(request: Request, req: SubtaxaMergeRequest) -> MergedSubtaxaResponse:
    result = merge_subtaxa(
        req.taxon_rang, req.taxon_nom, req.regne, [(s.module_id, s.liste) for s in req.sources]
    )

    adapter = ColXrAdapter()
    try:
        groups = await reconcile_synonym_groups(
            result.groups,
            [s.module_id for s in req.sources],
            lambda nom: resolve_col_xr_concept_id(adapter, nom, req.regne),
        )
    finally:
        await adapter.aclose()

    return MergedSubtaxaResponse(
        rang_txt=result.rang_txt,
        rang_txt_singulier=result.rang_txt_singulier,
        pronoun=result.pronoun,
        taxon_phrase=result.taxon_phrase,
        rang_names=result.rang_names,
        groups=[
            MergedGroupOut(
                sources=g.sources,
                kind=g.kind,
                intro=g.intro,
                species=[
                    MergedSpeciesOut(
                        nom=s.nom, rang=s.rang, line=s.line, default_checked=s.default_checked
                    )
                    for s in g.species
                ],
            )
            for g in groups
        ],
    )
