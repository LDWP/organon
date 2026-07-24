"""POST /api/v1/subtaxa-merge — fusionne les sous-taxons de plusieurs sources de classification
déjà résolues côté frontend (voir `organon.core.rendering.subtaxa_merge`), pour le mode de rendu
"sous-taxons fusionnés" de l'onglet Wikitexte. Aucun appel réseau ni résolution de taxon ici :
prend en entrée les listes déjà récupérées par le frontend (`resultsBySource`, voir
`GenerateResponse.subtaxa_liste`), ne recontacte aucun module de classification.
"""

from __future__ import annotations

from fastapi import APIRouter

from organon.api.schemas import (
    MergedGroupOut,
    MergedSpeciesOut,
    MergedSubtaxaResponse,
    SubtaxaMergeRequest,
)
from organon.core.rendering.subtaxa_merge import merge_subtaxa

router = APIRouter()


@router.post("/subtaxa-merge", response_model=MergedSubtaxaResponse)
async def subtaxa_merge(req: SubtaxaMergeRequest) -> MergedSubtaxaResponse:
    result = merge_subtaxa(
        req.taxon_rang, req.taxon_nom, req.regne, [(s.module_id, s.liste) for s in req.sources]
    )
    return MergedSubtaxaResponse(
        rang_txt=result.rang_txt,
        rang_txt_singulier=result.rang_txt_singulier,
        pronoun=result.pronoun,
        taxon_phrase=result.taxon_phrase,
        groups=[
            MergedGroupOut(
                sources=g.sources,
                kind=g.kind,
                intro=g.intro,
                species=[
                    MergedSpeciesOut(nom=s.nom, line=s.line, default_checked=s.default_checked)
                    for s in g.species
                ],
            )
            for g in result.groups
        ],
    )
