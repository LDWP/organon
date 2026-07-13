"""POST /api/v1/generate — orchestration de la génération : résout la classification,
l'exécute, puis exécute les modules non-classification applicables au domaine, calcule les
catégories/portails, résout l'auteur du taxon principal, puis rend le wikitexte.

La résolution complète de l'auteur (`resoudre_auteur_principal`) se fait ici plutôt qu'au
moment du rendu : elle a besoin de `struct.regne` (déjà résolu à ce stade) pour choisir la bonne
table (botanistes/procaryotes/zoologistes), et ses avertissements de désaccord de source
rejoignent la liste `warnings` de la réponse au même titre que ceux des modules.

POST /api/v1/generate/stream — même pipeline, exposé en Server-Sent Events (un `module_status`
par module de classification/enrichissement, un `plan` une fois la classification connue, puis
un `result` final identique au corps JSON de `/generate`) pour que le frontend affiche une
progression module par module plutôt qu'un seul état bloquant pendant les 10-20s que peut durer
une génération avec ~20 modules applicables. Voir `EnrichmentRunner` ci-dessous : la boucle
d'enrichissement est partagée par les deux endpoints (même ordre, mêmes messages
d'avertissement) pour que `/generate` reste identique en comportement — seul `/generate/stream`
observe les événements intermédiaires au lieu de les laisser s'accumuler silencieusement.

Hors périmètre pour l'instant : le mode `-juste-ext` (liens externes uniquement, sans
classification).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from organon.api.schemas import (
    ExternalLink,
    FatalErrorEvent,
    GenerateRequest,
    GenerateResponse,
    ModuleStatusEvent,
    PlanEvent,
    RankLine,
    ResultEvent,
)
from organon.core.config import GenerateOptions
from organon.core.domains import DomainTree, meilleure_classification, modules_possibles
from organon.core.models import Struct, TaxonInfo
from organon.core.registry import (
    TaxonomyModule,
    classification_modules,
    default_classification_module,
    get_module,
    module_domain_trees,
    module_priorities,
)
from organon.core.rendering.authors import resoudre_auteur_principal
from organon.core.rendering.engine import render, render_subtaxa_block, render_taxobox_block
from organon.core.rendering.sections import compute_rank_lines
from organon.core.rendering.support import ajoute_si_besoin
from organon.core.selectors.categorization import compute_fin_liens
from organon.core.selectors.coherence import detect_regne_incoherences
from organon.modules.bootstrap import ensure_modules_registered

router = APIRouter()
logger = logging.getLogger(__name__)


async def _collect_with_timeout(
    module: TaxonomyModule, struct: Struct, *, is_classification: bool, options: GenerateOptions
) -> Struct | None:
    """Appelle `module.collect(...)` en appliquant `options.timeout` (si non nul) à l'appel —
    seul endroit qui lit ce champ (voir `GenerateOptions.timeout`, jusqu'ici mort code). Un
    dépassement lève `TimeoutError` (alias `asyncio.TimeoutError` depuis Python 3.11), propagée
    à l'appelant exactement comme n'importe quelle autre exception réseau : capturée par le
    `try/except` dédié à la classification ci-dessous, ou par `EnrichmentRunner.run` pour
    l'enrichissement — pas de traitement spécial ici pour rester au plus près du contrat
    existant de `collect()`."""
    coro = module.collect(struct, is_classification=is_classification, options=options)
    if options.timeout > 0:
        return await asyncio.wait_for(coro, timeout=options.timeout)
    return await coro


def _options_from_request(req: GenerateRequest) -> GenerateOptions:
    return GenerateOptions(**req.model_dump(exclude={"taxon"}))


def _resolve_classification(
    req: GenerateRequest, off: set[str], trees: dict[str, DomainTree], priorities: dict[str, int]
) -> tuple[str, TaxonomyModule]:
    """Détermine le module de classification à utiliser et le renvoie déjà résolu depuis le
    registre. Ne fait aucun appel réseau (uniquement de la lecture de métadonnées) : peut donc
    être appelé avant d'ouvrir un `StreamingResponse`, pour que ces erreurs de configuration
    restent de vraies erreurs HTTP 400 plutôt que des événements SSE (le code de statut d'une
    réponse en streaming est figé dès le premier octet envoyé, voir `FatalErrorEvent`)."""
    classification_id = req.classification or meilleure_classification(
        req.domaine,
        classification_module_ids=[m for m in classification_modules() if m not in off],
        module_trees=trees,
        module_priorities=priorities,
        default_module=default_classification_module(),
    )
    if not classification_id:
        raise HTTPException(400, detail="Aucun module de classification disponible.")
    classification_module = get_module(classification_id)
    if classification_module is None or classification_id in off:
        raise HTTPException(400, detail=f"Module de classification '{classification_id}' inconnu ou désactivé.")
    return classification_id, classification_module


@dataclass
class ModuleRunEvent:
    """Un pas de progression émis par `EnrichmentRunner.run()` pour un module donné."""

    module_id: str
    status: str  # "running" | "found" | "empty" | "error"
    message: str | None = None


class EnrichmentRunner:
    """Exécute en séquence les modules d'enrichissement applicables (hors classification), en
    accumulant `struct`/`ran_modules`/`warnings` exactement comme le faisait la boucle `for`
    d'origine dans `generate()` — extrait ici uniquement pour que `/generate/stream` puisse
    observer un `ModuleRunEvent` par module sans dupliquer cette boucle (et donc sans risquer
    une divergence de comportement entre les deux endpoints)."""

    def __init__(
        self,
        struct: Struct,
        classification_id: str,
        applicable: list[str],
        off: set[str],
        options: GenerateOptions,
    ) -> None:
        self.struct = struct
        self.ran_modules: list[str] = [classification_id]
        self.warnings: list[str] = []
        self._classification_id = classification_id
        self._applicable = applicable
        self._off = off
        self._options = options

    async def run(self) -> AsyncIterator[ModuleRunEvent]:
        for module_id in self._applicable:
            if module_id == self._classification_id or module_id in self._off:
                continue
            module = get_module(module_id)
            if module is None:
                continue
            yield ModuleRunEvent(module_id, "running")
            try:
                updated = await _collect_with_timeout(
                    module, self.struct, is_classification=False, options=self._options
                )
                if updated is not None:
                    self.struct = updated
                    self.ran_modules.append(module_id)
                    yield ModuleRunEvent(module_id, "found")
                else:
                    # Pas d'entrée dans `self.warnings` : un module d'enrichissement qui ne
                    # trouve rien pour ce taxon est le cas courant (la plupart des ~20 modules
                    # ne couvrent qu'un domaine restreint), pas une anomalie à afficher dans le
                    # wikitexte final — le statut "empty" reste visible module par module via
                    # `ModuleRunEvent`/l'onglet Données côté frontend.
                    yield ModuleRunEvent(module_id, "empty")
            except Exception as exc:  # noqa: BLE001 — un module tiers en échec ne doit pas casser la génération
                logger.warning("Module '%s' (enrichissement) : erreur réseau (%s), ignoré.", module_id, exc)
                yield ModuleRunEvent(module_id, "error", message=str(exc))


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    ensure_modules_registered()
    started = time.monotonic()
    logs: list[str] = []
    warnings: list[str] = []
    options = _options_from_request(req)

    off = set(req.off)
    trees = module_domain_trees(exclude=off)
    priorities = module_priorities(exclude=off)

    classification_id, classification_module = _resolve_classification(req, off, trees, priorities)

    struct = Struct(taxon=TaxonInfo(nom=req.taxon), classification=req.classification, domaine=req.domaine)
    logs.append(f"Classification : {classification_id}")

    try:
        resolved = await _collect_with_timeout(
            classification_module, struct, is_classification=True, options=options
        )
    except Exception as exc:  # noqa: BLE001 — dégrade en erreur HTTP propre plutôt qu'un 500 non géré,
        # cohérent avec le traitement déjà en place côté /generate/stream (voir event_stream ci-dessous)
        logger.warning("Module de classification '%s' : erreur réseau (%s)", classification_id, exc)
        raise HTTPException(
            502, detail=f"Module de classification '{classification_id}' : erreur réseau ({exc})."
        ) from exc
    if resolved is None:
        raise HTTPException(
            404, detail=f"Taxon « {req.taxon} » non trouvé via la classification '{classification_id}'."
        )
    struct = resolved

    applicable = modules_possibles(struct.domaine, trees) or []
    runner = EnrichmentRunner(struct, classification_id, applicable, off, options)
    async for _event in runner.run():
        pass  # /generate ignore la progression intermédiaire ; /generate/stream l'observe.

    return _assemble_response(
        req, options, classification_id, runner.struct, runner.ran_modules, warnings + runner.warnings, logs, started
    )


def _auteur_majoritaire(struct: Struct) -> str:
    """Retient l'auteur que le plus de modules rapportent à l'identique, plutôt que celui du
    seul module de classification (qui peut très bien n'avoir rien trouvé alors qu'un module
    d'enrichissement, lui, a l'info — ex. classifier via OTL/iNaturalist, qui n'exposent pas
    l'auteur, alors que GBIF tourné en enrichissement l'a trouvé) ou le premier rencontré dans
    un ordre arbitraire. Aucune priorité de module : à effectif égal, l'auteur du module de
    classification l'emporte (c'est lui qui pilote cette génération), à défaut le premier
    rencontré. Les modules qui ne rapportent l'auteur que pour une fiche secondaire (ex. CoL,
    dont l'auteur vit sous `liens['col']['bundles']` en cas d'homonymie non résolue plutôt qu'au
    premier niveau) ne participent pas au vote, faute de porter l'auteur du taxon principal au
    même endroit que les autres modules."""
    classification_auteur = (struct.taxon.auteur or "").strip()
    candidats = [classification_auteur] if classification_auteur else []
    for data in struct.liens.values():
        auteur = data.get("auteur")
        if auteur:
            candidats.append(auteur.strip())

    if not candidats:
        return ""

    comptes: dict[str, int] = {}
    for c in candidats:
        comptes[c] = comptes.get(c, 0) + 1
    meilleur_effectif = max(comptes.values())
    ex_aequo = [c for c in candidats if comptes[c] == meilleur_effectif]
    return classification_auteur if classification_auteur in ex_aequo else ex_aequo[0]


def _compute_data_found(struct: Struct, classification_id: str) -> dict[str, list[str]]:
    """Pour chaque module, les catégories d'information qu'il a effectivement rapportées pour
    ce taxon (ex. "Classification", "Taxons inférieurs", "Auteur"...) — dérivé directement des
    champs déjà peuplés de `struct` (quel module est `struct.sous_taxons.source`, quelles clés
    de `struct.vernaculaire`/`struct.distribution` sont non vides...) plutôt qu'une liste
    maintenue à la main module par module. Sert de base à `GenerateResponse.data_found`."""
    found: dict[str, list[str]] = {classification_id: ["Classification"]}

    def add(module_id: str | None, label: str) -> None:
        if not module_id:
            return
        labels = found.setdefault(module_id, [])
        if label not in labels:
            labels.append(label)

    if struct.sous_taxons and struct.sous_taxons.liste:
        add(struct.sous_taxons.source, "Taxons inférieurs")
    if struct.synonymes and struct.synonymes.liste:
        add(struct.synonymes.source, "Synonymes")
    if struct.basionyme:
        add(struct.basionyme.source, "Basionyme")
    if struct.type_taxon:
        add(struct.type_taxon.source, "Taxon type")
    if struct.etymologie:
        add(struct.etymologie.source, "Étymologie")
    for module_id, entry in struct.distribution.items():
        if entry.certain or entry.uncertain:
            add(module_id, "Répartition")
    for module_id, noms in struct.vernaculaire.items():
        if noms:
            add(module_id, "Noms vernaculaires")
    for module_id, data in struct.liens.items():
        if data.get("auteur"):
            add(module_id, "Auteur")

    return found


def _assemble_response(
    req: GenerateRequest,
    options: GenerateOptions,
    classification_id: str,
    struct: Struct,
    ran_modules: list[str],
    warnings: list[str],
    logs: list[str],
    started: float,
) -> GenerateResponse:
    """Étapes finales communes aux deux endpoints, une fois tous les modules d'enrichissement
    exécutés : incohérences de règne, catégories/portails, auteur principal, rendu du
    wikitexte, liens externes, réponse. Ne fait plus aucun appel réseau (uniquement du calcul
    local) : peut donc être appelée telle quelle depuis le générateur SSE de `/generate/stream`
    sans considération de streaming."""
    regne_incoherences = detect_regne_incoherences(struct, classification_id)

    struct.liens["fin"] = compute_fin_liens(struct, options)

    struct.taxon.auteur = _auteur_majoritaire(struct)
    struct.taxon.auteur_resolu, auteur_warnings = resoudre_auteur_principal(struct)
    warnings = warnings + auteur_warnings

    wikitext = render(struct, options, ext_only=req.juste_ext)
    taxobox_wikitext = "" if req.juste_ext else render_taxobox_block(struct, options)
    subtaxa_wikitext = "" if req.juste_ext else render_subtaxa_block(struct, options)
    rank_lines = (
        []
        if req.juste_ext
        else [RankLine(rang=r, nom=n, line=line) for r, n, line in compute_rank_lines(struct)]
    )

    external_links = []
    for module_id in ran_modules:
        module = get_module(module_id)
        if module is None:
            continue
        link = module.debug_link(struct)
        if link:
            external_links.append(ExternalLink(module_id=module_id, html=link))

    truncated = {
        "sous_taxons": bool(struct.sous_taxons and struct.sous_taxons.coupe),
        "synonymes": bool(struct.synonymes and struct.synonymes.coupe),
    }

    vernacular_merged: dict[str, list[str]] = {}
    for src, noms in struct.vernaculaire.items():
        for nom in noms:
            ajoute_si_besoin(vernacular_merged, nom, src)

    # Anciennement un unique `completeness_score` (rangs + sous-taxons + synonymes + noms
    # vernaculaires additionnés) : scindé en deux mesures indépendantes, une par facette du
    # "zoom" classification (taxobox / sous-taxons), pour que le frontend puisse recommander une
    # source différente pour chaque facette plutôt qu'une seule source "la plus complète" au
    # global. Synonymes et noms vernaculaires ne rentrent dans aucune des deux mesures : ils ne
    # font partie ni du bloc taxobox ni du bloc sous-taxons (voir `taxobox_wikitext`/
    # `subtaxa_wikitext`), donc les compter ferait pencher un score sans rapport avec ce qu'il
    # sert à choisir.
    taxobox_completeness_score = len(struct.rangs)
    subtaxa_completeness_score = len(struct.sous_taxons.liste if struct.sous_taxons else [])

    data_found = _compute_data_found(struct, classification_id)

    return GenerateResponse(
        taxon_requested=req.taxon,
        taxon_resolved=struct.taxon.nom,
        classification_used=classification_id,
        domain_used=struct.domaine,
        regne=struct.regne,
        eteint=bool(struct.taxon.eteint),
        vernacular_names=list(vernacular_merged)[:6],
        wikitext=wikitext,
        taxobox_wikitext=taxobox_wikitext,
        subtaxa_wikitext=subtaxa_wikitext,
        taxobox_completeness_score=taxobox_completeness_score,
        subtaxa_completeness_score=subtaxa_completeness_score,
        rank_lines=rank_lines,
        external_links=external_links,
        data_found=data_found,
        logs=logs,
        warnings=warnings,
        elapsed_seconds=round(time.monotonic() - started, 3),
        truncated=truncated,
        regne_incoherences=regne_incoherences,
    )


def _sse(event: BaseModel) -> str:
    """Encode un événement (`ModuleStatusEvent`/`PlanEvent`/`ResultEvent`/`FatalErrorEvent`) au
    format Server-Sent Events (une ligne `data: <json>`, suivie d'une ligne vide qui marque la
    fin de l'événement — voir la spec WHATWG). Passer par les modèles Pydantic plutôt que des
    dicts construits à la main garantit que chaque événement respecte le schéma documenté dans
    `organon/api/schemas.py` (ex. `status` limité aux quatre valeurs attendues) — une divergence
    lèverait une `ValidationError` ici plutôt qu'un event mal formé silencieusement envoyé au
    client. `ensure_ascii` volontairement laissé à sa valeur par défaut (True) : les caractères
    non-ASCII (noms de taxons accentués, etc.) passent en échappement \\uXXXX plutôt qu'en
    UTF-8 brut, ce qui évite tout risque de couper un caractère multi-octets au milieu si le
    corps de la réponse est un jour re-découpé par un proxy intermédiaire."""
    return f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"


@router.post("/generate/stream")
async def generate_stream(req: GenerateRequest) -> StreamingResponse:
    """Variante de `/generate` en Server-Sent Events : un `module_status` par module de
    classification/enrichissement (voir `ModuleStatusEvent`), un `plan` juste après la
    classification, puis un `result` final portant la même donnée que `POST /generate`. En cas
    d'échec après le début du flux (taxon non trouvé, erreur réseau sur la classification), un
    `fatal_error` est émis à la place du `result` — le code de statut HTTP reste 200 dans tous
    les cas puisqu'il est déjà envoyé au moment où le premier octet du flux part (voir
    `FatalErrorEvent`). Les erreurs de configuration qui ne dépendent d'aucun appel réseau (ex.
    module de classification inconnu) restent de vraies erreurs HTTP, levées par
    `_resolve_classification` avant l'ouverture du flux.
    """
    ensure_modules_registered()
    options = _options_from_request(req)
    off = set(req.off)
    trees = module_domain_trees(exclude=off)
    priorities = module_priorities(exclude=off)
    classification_id, classification_module = _resolve_classification(req, off, trees, priorities)

    async def event_stream() -> AsyncIterator[str]:
        started = time.monotonic()
        logs = [f"Classification : {classification_id}"]
        warnings: list[str] = []

        yield _sse(ModuleStatusEvent(module_id=classification_id, role="classification", status="running"))

        struct = Struct(taxon=TaxonInfo(nom=req.taxon), classification=req.classification, domaine=req.domaine)
        try:
            resolved = await _collect_with_timeout(
                classification_module, struct, is_classification=True, options=options
            )
        except Exception as exc:  # noqa: BLE001 — voir docstring : converti en événement, pas en exception ASGI
            logger.warning("Module de classification '%s' : erreur réseau (%s)", classification_id, exc)
            yield _sse(
                ModuleStatusEvent(
                    module_id=classification_id, role="classification", status="error", message=str(exc)
                )
            )
            yield _sse(
                FatalErrorEvent(
                    status_code=502,
                    detail=f"Module de classification '{classification_id}' : erreur réseau ({exc}).",
                )
            )
            return

        if resolved is None:
            yield _sse(
                ModuleStatusEvent(
                    module_id=classification_id, role="classification", status="error", message="taxon non trouvé"
                )
            )
            yield _sse(
                FatalErrorEvent(
                    status_code=404,
                    detail=f"Taxon « {req.taxon} » non trouvé via la classification '{classification_id}'.",
                )
            )
            return
        struct = resolved
        yield _sse(ModuleStatusEvent(module_id=classification_id, role="classification", status="found"))

        applicable = modules_possibles(struct.domaine, trees) or []
        enrichment_ids = [
            m for m in applicable if m != classification_id and m not in off and get_module(m) is not None
        ]
        yield _sse(PlanEvent(classification_id=classification_id, modules=enrichment_ids))

        runner = EnrichmentRunner(struct, classification_id, applicable, off, options)
        async for module_event in runner.run():
            yield _sse(
                ModuleStatusEvent(
                    module_id=module_event.module_id,
                    role="enrichment",
                    status=module_event.status,
                    message=module_event.message,
                )
            )

        response = _assemble_response(
            req, options, classification_id, runner.struct, runner.ran_modules, warnings + runner.warnings, logs, started
        )
        yield _sse(ResultEvent(data=response))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # Empêche un proxy intermédiaire (ex. nginx en frontal de certains hébergements) de
            # bufferiser la réponse en entier avant de la relayer — sans ça, le flux perdrait
            # tout son intérêt (le client ne verrait qu'un seul paquet final, comme /generate).
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
