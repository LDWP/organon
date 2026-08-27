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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from organon.api.deps import require_username
from organon.api.schemas import (
    ExternalLink,
    FatalErrorEvent,
    GenerateRequest,
    GenerateResponse,
    ModuleStatusEvent,
    PlanEvent,
    RankLine,
    ReferenceItem,
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
from organon.core.rendering.engine import (
    render,
    render_references_items_block,
    render_subtaxa_block,
    render_taxobox_block,
)
from organon.core.rendering.sections import compute_rank_lines
from organon.core.rendering.support import ajoute_si_besoin, data_pays_code
from organon.core.selectors.categorization import compute_fin_liens
from organon.core.selectors.coherence import (
    classification_regne_coherents,
    detect_regne_incoherences,
    gbif_annee_probable_validee,
    reference_module_coherente,
)
from organon.modules.bootstrap import ensure_modules_registered

router = APIRouter()
logger = logging.getLogger(__name__)

_MONOVALUE_FIELDS = (
    "classification",
    "classification_taxobox",
    "regne",
    "redirection",
    "rangs",
    "basionyme",
    "sous_taxons",
    "etymologie",
    "originale",
    "synonymes",
    "type_taxon",
    "cacher_regne",
    "image",
    "milieu",
    "taxon",
)
"""Champs mono-valeur de `Struct` que plusieurs modules d'enrichissement peuvent chacun vouloir
écrire (contrairement à `liens`/`vernaculaire`/`distribution`, déjà namespacés par module). Un
module n'a modifié un de ces champs, par rapport à la struct de base pré-enrichissement, que si
sa valeur diffère de celle de `_BASELINE` — voir `EnrichmentRunner.run` pour la fusion."""


_CLASSIFICATION_FALLBACK_TIMEOUT = 20.0
"""Borne (s) par tentative de classification quand `options.timeout` vaut 0 (défaut jamais changé
par le frontend) — sans ça, un module lancé en parallèle des autres peut bloquer la recherche
entière indéfiniment plutôt que de céder la place aux modules qui répondent."""


async def _collect_with_timeout(
    module: TaxonomyModule,
    struct: Struct,
    *,
    is_classification: bool,
    options: GenerateOptions,
    fallback_timeout: float | None = None,
) -> Struct | None:
    """Applique `options.timeout` si non nul, sinon `fallback_timeout`, autour de
    `module.collect(...)` (seul endroit qui lit `GenerateOptions.timeout`)."""
    coro = module.collect(struct, is_classification=is_classification, options=options)
    timeout = options.timeout if options.timeout > 0 else fallback_timeout
    if timeout:
        return await asyncio.wait_for(coro, timeout=timeout)
    return await coro


def _options_from_request(req: GenerateRequest) -> GenerateOptions:
    return GenerateOptions(**req.model_dump(exclude={"taxon"}))


def _all_applicable_classification_modules(
    domaine: str, off: set[str], trees: dict[str, DomainTree]
) -> list[tuple[str, TaxonomyModule]]:
    applicable = set(modules_possibles(domaine, trees) or [])
    candidates = [(m, get_module(m)) for m in classification_modules() if m in applicable and m not in off]
    return [(m, module) for m, module in candidates if module is not None]


def _classification_candidates(
    req: GenerateRequest, off: set[str], trees: dict[str, DomainTree], priorities: dict[str, int]
) -> list[tuple[str, TaxonomyModule]]:
    """Modules de classification à interroger en parallèle. Choix explicite
    (`req.classification`, ex. facette de source ou désambiguïsation GBIF) : un seul candidat —
    voir `_classification_network_fallback` pour le repli si celui-ci échoue au réseau. Sinon :
    tous les modules applicables au domaine demandé, aucun privilégié a priori (voir
    `_pick_classification_winner`)."""
    if req.classification:
        module = get_module(req.classification)
        if module is None or req.classification in off:
            raise HTTPException(
                400, detail=f"Module de classification '{req.classification}' inconnu ou désactivé."
            )
        return [(req.classification, module)]

    candidates = _all_applicable_classification_modules(req.domaine, off, trees)
    if not candidates:
        raise HTTPException(400, detail="Aucun module de classification disponible.")
    return candidates


def _classification_network_fallback(
    req: GenerateRequest, off: set[str], trees: dict[str, DomainTree], tried: dict[str, tuple]
) -> list[tuple[str, TaxonomyModule]]:
    """Un choix explicite qui échoue par erreur réseau (pas un "non trouvé", un signal fiable
    qu'on respecte tel quel) n'est pas la faute du taxon — retente les autres modules
    applicables plutôt que d'abandonner sur la seule panne d'un module."""
    if not (req.classification and all(exc is not None for _, exc in tried.values())):
        return []
    return [
        (m, module)
        for m, module in _all_applicable_classification_modules(req.domaine, off, trees)
        if m not in tried
    ]


async def _attempt_classification(
    module_id: str, module: TaxonomyModule, req: GenerateRequest, options: GenerateOptions
) -> tuple[str, Struct | None, Exception | None]:
    """Ne lève jamais (même contrat que `EnrichmentRunner.collect_one_module`) : le résultat
    porte l'erreur éventuelle plutôt que de la laisser se propager hors du `gather`/
    `as_completed`."""
    struct = Struct(taxon=TaxonInfo(nom=req.taxon), classification=req.classification, domaine=req.domaine)
    try:
        resolved = await _collect_with_timeout(
            module,
            struct,
            is_classification=True,
            options=options,
            fallback_timeout=_CLASSIFICATION_FALLBACK_TIMEOUT,
        )
        return module_id, resolved, None
    except Exception as exc:  # noqa: BLE001 — dégradé en HTTPException par l'appelant
        logger.warning("Module de classification '%s' : erreur réseau (%s)", module_id, exc)
        return module_id, None, exc


async def _run_classification_batch(
    batch: list[tuple[str, TaxonomyModule]],
    req: GenerateRequest,
    options: GenerateOptions,
    results: dict[str, tuple[Struct | None, Exception | None]],
    started: float,
) -> AsyncIterator[str]:
    """Lance un lot de candidats de classification en parallèle, en écrivant chaque résultat
    dans `results` au fil de l'eau — partagé par le lot initial et le repli réseau de
    `_classification_network_fallback` dans `event_stream()`."""
    for cid, _ in batch:
        yield _sse(ModuleStatusEvent(module_id=cid, role="classification", status="running"))
    tasks = [asyncio.create_task(_attempt_classification(cid, cm, req, options)) for cid, cm in batch]
    for task in asyncio.as_completed(tasks):
        module_id, resolved, exc = await task
        results[module_id] = (resolved, exc)
        if exc is not None:
            status, message = "error", str(exc)
        elif resolved is None:
            status, message = "error", "taxon non trouvé"
        else:
            status, message = "found", None
        yield _sse(
            ModuleStatusEvent(
                module_id=module_id,
                role="classification",
                status=status,
                message=message,
                duration_seconds=time.monotonic() - started,
            )
        )


def _pick_classification_winner(
    domaine: str,
    successes: list[str],
    trees: dict[str, DomainTree],
    priorities: dict[str, int],
    results: dict[str, tuple[Struct | None, Exception | None]],
) -> tuple[str, list[str]]:
    """Départage les modules de classification ayant réussi — par spécialisation au domaine
    demandé (`meilleure_classification`), ou par simple priorité quand cette notion ne
    s'applique pas (un seul candidat retenu, ou aucun règne majoritaire exploitable sans filtre).

    Écarte d'abord les candidats dont le règne est minoritaire face aux autres candidats
    (`classification_regne_coherents` — voir docstring pour la définition de majorité retenue) :
    un module plus spécialisé ou prioritaire ne doit pas l'emporter au détriment de la
    cohérence globale si son résultat est un homonyme inter-règnes minoritaire. Retourne
    également la liste des candidats ainsi écartés, pour que l'appelant en informe l'utilisateur
    plutôt que de les faire disparaître silencieusement.

    Sans filtre explicite (`domaine == "*"`), le règne majoritaire détecté par les modules eux-
    mêmes (ex. GBIF/ITIS/WoRMS) sert de domaine de facto pour `meilleure_classification` — un
    module spécialisé (LPSN pour une bactérie, POWO pour une plante...) doit l'emporter sur un
    généraliste mieux priorisé même quand l'utilisateur n'a rien filtré à la recherche."""
    regnes = {cid: results[cid][0].regne for cid in successes if results[cid][0] is not None}
    coherents, exclus, regne_majoritaire = classification_regne_coherents(successes, regnes)
    pool = coherents or successes

    if domaine == "*" and regne_majoritaire:
        domaine = regne_majoritaire

    if len(pool) == 1 or domaine == "*":
        return max(pool, key=lambda m: priorities.get(m, 0)), exclus
    winner = meilleure_classification(
        domaine,
        classification_module_ids=pool,
        module_trees=trees,
        module_priorities=priorities,
        default_module=default_classification_module(),
    )
    return winner, exclus


def _avertissements_exclusion_regne(
    exclus: list[str], results: dict[str, tuple[Struct | None, Exception | None]]
) -> list[str]:
    """Un candidat de classification écarté par `_pick_classification_winner` pour règne
    minoritaire a bel et bien trouvé quelque chose (ex. ITIS retrouvant un homonyme bactérien
    pour un genre de champignon) — le signaler plutôt que le faire disparaître silencieusement,
    au même titre que les autres avertissements affichés dans le panneau Données."""
    return [
        f"{cid.upper()} écarté de la classification : règne « {results[cid][0].regne} » minoritaire "
        f"face aux autres sources (possible homonyme inter-règnes)."
        for cid in exclus
        if results[cid][0] is not None
    ]


@dataclass
class ModuleRunEvent:
    """Un pas de progression émis par `EnrichmentRunner.run()` pour un module donné."""

    module_id: str
    status: str  # "running" | "found" | "empty" | "error"
    message: str | None = None
    duration_seconds: float | None = None


class EnrichmentRunner:
    """Exécute en parallèle les modules d'enrichissement applicables (hors classification), en
    accumulant `struct`/`ran_modules`/`warnings` — extrait ici uniquement pour que
    `/generate/stream` puisse observer un `ModuleRunEvent` par module sans dupliquer cette
    logique (et donc sans risquer une divergence de comportement entre les deux endpoints). Voir
    `run()` pour l'ordre de fusion des résultats."""

    def __init__(
        self,
        struct: Struct,
        classification_id: str,
        applicable: list[str],
        off: set[str],
        options: GenerateOptions,
        priorities: dict[str, int],
    ) -> None:
        self.struct = struct
        self._baseline = struct.model_copy(deep=True)
        """Snapshot pré-enrichissement, pour distinguer un champ mono-valeur effectivement écrit
        par un module d'un champ resté inchangé (voir `_MONOVALUE_FIELDS`)."""
        self.ran_modules: list[str] = [classification_id]
        self.warnings: list[str] = []
        self._options = options
        # Filtré une fois ici (classification déjà traitée séparément, modules désactivés ou
        # inconnus) plutôt que dans `run()`, pour ne créer une task et émettre un `ModuleRunEvent`
        # "running" que pour les modules réellement interrogés. Trié par priorité croissante :
        # `run()` applique les résultats dans cet ordre, donc le module le plus prioritaire est
        # traité en dernier et l'emporte sur les autres en cas de conflit sur un champ mono-valeur
        # (voir `_MONOVALUE_FIELDS`). Avant ce tri, l'ordre était celui d'enregistrement des
        # modules dans `bootstrap.py` (alphabétique), sans rapport avec `ModuleMeta.priority`.
        candidates = [
            m
            for m in applicable
            if m != classification_id and m not in off and get_module(m) is not None
        ]
        self._enrichment_ids = sorted(candidates, key=lambda m: priorities.get(m, 0))

    async def collect_one_module(
        self, module_id: str
    ) -> tuple[str, Struct | None, Exception | None]:
        """Ne lève jamais : le résultat porte l'erreur éventuelle plutôt que de la laisser se
        propager, pour que `run()` puisse identifier de façon fiable quel module a échoué —
        `asyncio.as_completed` ne préserve pas l'identité des tasks qu'on lui passe (il renvoie
        des wrappers internes), donc retrouver `module_id` après coup via un mapping tâche ->
        id, ou via l'unpacking d'un tuple qui échouerait avant d'avoir été produit, ne marche
        pas de façon fiable en cas d'exception.

        Chaque module reçoit sa propre copie profonde de `self.struct` plutôt que l'objet
        partagé : les modules mutent `struct` en place (`Struct` a été conçu pour un pipeline
        séquentiel, voir sa docstring), donc en exécution concurrente deux modules qui écrivent
        au même moment le même champ mono-valeur produiraient un résultat dépendant de
        l'entrelacement de la boucle d'événements plutôt que de la priorité déclarée — `run()`
        fusionne ensuite ces copies indépendantes dans l'ordre de priorité."""
        module = get_module(module_id)
        try:
            updated = await _collect_with_timeout(
                module, self.struct.model_copy(deep=True), is_classification=False, options=self._options
            )
            return module_id, updated, None
        except Exception as exc:  # noqa: BLE001 — un module tiers en échec ne doit pas casser la génération
            return module_id, None, exc

    async def run(self) -> AsyncIterator[ModuleRunEvent]:
        """Lance tous les modules d'enrichissement en parallèle sur la même base `struct` (celle
        laissée par la classification) et notifie leur progression au fil de l'eau via
        `asyncio.as_completed`, mais n'applique leurs résultats à `self.struct`/`self.ran_modules`
        qu'une fois tous terminés, dans l'ordre de priorité `_enrichment_ids` plutôt que dans
        l'ordre d'arrivée réseau. Sans ça, deux modules qui écrivent le même champ mono-valeur de
        `Struct` (`sous_taxons`, `synonymes`, `basionyme`...) donneraient un résultat dépendant de
        la latence de chacun plutôt que de la priorité déclarée. Les champs déjà namespacés par
        module (`liens`, `vernaculaire`, `autres_noms`, `distribution`) n'ont pas ce problème —
        chaque copie ne porte que la clé de son propre module, donc un simple `update()` les
        fusionne sans conflit ; seuls les champs mono-valeur de `_MONOVALUE_FIELDS` nécessitent
        un choix par priorité, tranché en comparant chaque copie à `self._baseline`."""
        started: dict[str, float] = {module_id: time.monotonic() for module_id in self._enrichment_ids}
        tasks = [
            asyncio.create_task(self.collect_one_module(module_id), name=module_id)
            for module_id in self._enrichment_ids
        ]
        for module_id in self._enrichment_ids:
            yield ModuleRunEvent(module_id, "running")

        results: dict[str, Struct] = {}
        for task in asyncio.as_completed(tasks):
            module_id, updated, exc = await task
            duration = time.monotonic() - started[module_id]
            if exc is not None:
                logger.warning(
                    "Module '%s' (enrichissement) : erreur réseau (%s), ignoré.", module_id, exc
                )
                yield ModuleRunEvent(module_id, "error", message=str(exc), duration_seconds=duration)
            elif updated is not None:
                results[module_id] = updated
                yield ModuleRunEvent(module_id, "found", duration_seconds=duration)
            else:
                # Pas d'entrée dans `self.warnings` : un module d'enrichissement qui ne
                # trouve rien pour ce taxon est le cas courant (la plupart des ~20 modules
                # ne couvrent qu'un domaine restreint), pas une anomalie à afficher dans le
                # wikitexte final — le statut "empty" reste visible module par module via
                # `ModuleRunEvent`/l'onglet Données côté frontend.
                yield ModuleRunEvent(module_id, "empty", duration_seconds=duration)

        for module_id in self._enrichment_ids:
            if module_id not in results:
                continue
            copy = results[module_id]
            self.struct.liens.update(copy.liens)
            self.struct.vernaculaire.update(copy.vernaculaire)
            self.struct.autres_noms.update(copy.autres_noms)
            self.struct.distribution.update(copy.distribution)
            for field in _MONOVALUE_FIELDS:
                value = getattr(copy, field)
                if value != getattr(self._baseline, field):
                    setattr(self.struct, field, value)
            self.ran_modules.append(module_id)


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, username: str = Depends(require_username)) -> GenerateResponse:
    ensure_modules_registered()
    started = time.monotonic()
    logs: list[str] = []
    warnings: list[str] = []
    options = _options_from_request(req)

    off = set(req.off)
    trees = module_domain_trees(exclude=off)
    priorities = module_priorities(exclude=off)

    candidates = _classification_candidates(req, off, trees, priorities)
    attempts = await asyncio.gather(*(_attempt_classification(cid, cm, req, options) for cid, cm in candidates))
    results = {cid: (resolved, exc) for cid, resolved, exc in attempts}

    fallback = _classification_network_fallback(req, off, trees, results)
    if fallback:
        fallback_attempts = await asyncio.gather(
            *(_attempt_classification(cid, cm, req, options) for cid, cm in fallback)
        )
        results.update({cid: (resolved, exc) for cid, resolved, exc in fallback_attempts})

    successes = [cid for cid, (resolved, _) in results.items() if resolved is not None]

    if not successes:
        if all(exc is not None for _, exc in results.values()):
            raise HTTPException(
                502, detail=f"Modules de classification en erreur réseau : {', '.join(sorted(results))}."
            )
        raise HTTPException(
            404, detail=f"Taxon « {req.taxon} » non trouvé (classifications essayées : {', '.join(sorted(results))})."
        )

    classification_id, exclus_regne = _pick_classification_winner(req.domaine, successes, trees, priorities, results)
    struct = results[classification_id][0]
    logs.append(f"Classification : {classification_id}")
    warnings.extend(_avertissements_exclusion_regne(exclus_regne, results))

    applicable = modules_possibles(struct.domaine, trees) or []
    runner = EnrichmentRunner(struct, classification_id, applicable, off, options, priorities)
    async for _event in runner.run():
        pass  # /generate ignore la progression intermédiaire ; /generate/stream l'observe.

    return _assemble_response(
        req, options, classification_id, runner.struct, runner.ran_modules, warnings + runner.warnings, logs, started
    )


@router.get("/generate", response_model=GenerateResponse)
async def generate_via_get(taxon: str, username: str = Depends(require_username)) -> GenerateResponse:
    """Alias GET de `POST /generate`, avec uniquement `taxon` en paramètre de requête (toutes
    les autres options à leur valeur par défaut) — pour pouvoir déclencher une génération
    depuis un simple lien ou la barre d'adresse d'un navigateur, sans construire de corps JSON.
    Le frontend continue d'utiliser `POST /generate`/`POST /generate/stream`, qui exposent
    l'intégralité de `GenerateOptions`.

    `username` résolu ici puis passé explicitement à `generate()` : appelée directement comme une
    coroutine Python plutôt que via une requête HTTP, cette dernière ne repasserait jamais par la
    résolution FastAPI de son propre `Depends(require_username)`."""
    return await generate(GenerateRequest(taxon=taxon), username=username)


def _auteur_candidats(struct: Struct, classification_id: str) -> dict[str, str]:
    """Auteur brut rapporté par chaque module ayant contribué à ce taxon, avant vote majoritaire
    — exposé via `GenerateResponse.auteur_candidats` pour permettre à l'utilisateur d'imposer une
    source via `GenerateOptions.auteur_source` plutôt que de subir le vote automatique de
    `_auteur_majoritaire`. Même périmètre que ce vote, mais un candidat par module plutôt qu'un
    multi-ensemble : ici seule la liste des sources disponibles compte, pas leur poids dans un
    vote."""
    candidats: dict[str, str] = {}
    classification_auteur = (struct.taxon.auteur or "").strip()
    if classification_auteur:
        candidats[classification_id] = classification_auteur
    for module_id, data in struct.liens.items():
        auteur = data.get("auteur")
        if auteur:
            candidats[module_id] = auteur.strip()
    return candidats


def _auteur_majoritaire(struct: Struct, classification_id: str) -> str:
    """Retient l'auteur que le plus de modules rapportent à l'identique, plutôt que celui du
    seul module de classification (qui peut très bien n'avoir rien trouvé alors qu'un module
    d'enrichissement, lui, a l'info — ex. classifier via OTL/iNaturalist, qui n'exposent pas
    l'auteur, alors que GBIF tourné en enrichissement l'a trouvé) ou le premier rencontré dans
    un ordre arbitraire. Aucune priorité de module : à effectif égal, l'auteur du module de
    classification l'emporte (c'est lui qui pilote cette génération), à défaut le premier
    rencontré."""
    classification_auteur = (struct.taxon.auteur or "").strip()
    candidats = [classification_auteur] if classification_auteur else []
    for module_id, data in struct.liens.items():
        if module_id == classification_id:
            continue  # déjà compté via classification_auteur — sinon double voix pour ce module
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


def _compute_external_ids(struct: Struct, ran_modules: list[str]) -> dict[str, str]:
    """Identifiant du taxon par module ayant contribué à cette génération — convention
    `struct.liens[module_id]['id']` suivie par tous les modules (voir
    `organon.modules.common.simple_debug_link`). Un module dont l'entrée ne porte pas cette clé
    (ex. `externe`, qui ne référence aucune base externe propre) est simplement absent du
    résultat."""
    ids: dict[str, str] = {}
    for module_id in ran_modules:
        data = struct.liens.get(module_id)
        if not isinstance(data, dict):
            continue
        if data.get("id"):
            ids[module_id] = str(data["id"])
    return ids


def _repli_eteint(struct: Struct) -> None:
    """Filet de sécurité : la source de classification retenue peut n'avoir aucun signal
    d'extinction pour ce taxon (ex. Hesperomys sans `age` renseigné à ce rang) alors qu'une
    autre source consultée en enrichissement le sait (`isExtinct`/`isFossil`/`extinct` -> `True`
    dans `struct.liens[<module>]["eteint"]`, voir modules irmng/wrms/algaebase/gbif/hesperomys).
    Seul un `True` explicite compte : l'affichage ne distingue pas "non éteint" de "inconnu", donc
    inutile de chercher un `False` à faire gagner. En revanche un `False` explicite de la source
    de classification (elle a une opinion, contrairement à `None`) n'est pas écrasé : seule
    l'absence de signal déclenche le repli."""
    if struct.taxon.eteint is not None:
        return
    if any(entry.get("eteint") for entry in struct.liens.values()):
        struct.taxon.eteint = True


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
    _repli_eteint(struct)
    regne_incoherences = detect_regne_incoherences(struct, classification_id)

    struct.liens["fin"] = compute_fin_liens(struct, options)

    auteur_candidats = _auteur_candidats(struct, classification_id)
    if options.auteur_source and options.auteur_source in auteur_candidats:
        struct.taxon.auteur = auteur_candidats[options.auteur_source]
    else:
        struct.taxon.auteur = _auteur_majoritaire(struct, classification_id)
    # Année GBIF (parsing de `publishedIn`, texte libre — voir gbif/module.py::_annee_probable) :
    # ajoutée seulement si un autre module rapporte la même année dans son propre auteur (voir
    # gbif_annee_probable_validee), jamais présentée à l'utilisateur sur la seule foi du parsing.
    annee_gbif_validee = gbif_annee_probable_validee(struct, struct.taxon.auteur)
    if annee_gbif_validee is not None:
        struct.taxon.auteur = f"{struct.taxon.auteur}, {annee_gbif_validee}"
    struct.taxon.auteur_resolu, auteur_warnings = resoudre_auteur_principal(struct)
    warnings = warnings + auteur_warnings

    wikitext = render(struct, options, ext_only=req.juste_ext)
    taxobox_wikitext = "" if req.juste_ext else render_taxobox_block(struct, options)
    subtaxa_wikitext = "" if req.juste_ext else render_subtaxa_block(struct, options)
    reference_items = [
        ReferenceItem(
            module_id=module_id,
            wikitext=wikitext,
            default_checked=reference_module_coherente(module_id, struct.regne),
        )
        for module_id, wikitext in render_references_items_block(struct)
    ]
    references_wikitext = (
        "\n".join(f"* {item.wikitext}" for item in reference_items) + "\n" if reference_items else ""
    )
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

    autres_noms_merged: dict[str, dict[str, list[str]]] = {}
    for src, statuts in struct.autres_noms.items():
        for statut, noms in statuts.items():
            bucket = autres_noms_merged.setdefault(statut, {})
            for nom in noms:
                ajoute_si_besoin(bucket, nom, src)
    autres_noms_response = {statut: list(noms) for statut, noms in autres_noms_merged.items()}

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

    distribution_merged: dict[str, list[str]] = {}
    for module_id, entry in struct.distribution.items():
        noms = sorted(dict.fromkeys(data_pays_code(code) for code in {**entry.certain, **entry.uncertain}))
        if noms:
            distribution_merged[module_id] = noms

    return GenerateResponse(
        taxon_requested=req.taxon,
        taxon_resolved=struct.taxon.nom,
        taxon_rang=struct.taxon.rang or "",
        classification_used=classification_id,
        domain_used=struct.domaine,
        regne=struct.regne,
        eteint=bool(struct.taxon.eteint),
        uicn_statut=struct.liens.get("uicn", {}).get("risque", ""),
        vernacular_names=list(vernacular_merged)[:6],
        autres_noms=autres_noms_response,
        wikitext=wikitext,
        taxobox_wikitext=taxobox_wikitext,
        subtaxa_wikitext=subtaxa_wikitext,
        subtaxa_liste=struct.sous_taxons.liste if struct.sous_taxons else [],
        references_wikitext=references_wikitext,
        reference_items=reference_items,
        taxobox_completeness_score=taxobox_completeness_score,
        subtaxa_completeness_score=subtaxa_completeness_score,
        rank_lines=rank_lines,
        external_links=external_links,
        data_found=data_found,
        auteur_candidats=auteur_candidats,
        auteur_consolide=struct.taxon.auteur or "",
        auteur_resolu=struct.taxon.auteur_resolu or "",
        synonymes=struct.synonymes.liste if struct.synonymes else [],
        synonymes_source=struct.synonymes.source if struct.synonymes else "",
        basionyme=struct.basionyme,
        logs=logs,
        warnings=warnings,
        elapsed_seconds=round(time.monotonic() - started, 3),
        truncated=truncated,
        regne_incoherences=regne_incoherences,
        milieu=struct.milieu or "",
        distribution=distribution_merged,
        external_ids=_compute_external_ids(struct, ran_modules),
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
async def generate_stream(req: GenerateRequest, username: str = Depends(require_username)) -> StreamingResponse:
    """Variante de `/generate` en Server-Sent Events : un `module_status` par module de
    classification/enrichissement (voir `ModuleStatusEvent`), un `plan` juste après la
    classification, puis un `result` final portant la même donnée que `POST /generate`. En cas
    d'échec après le début du flux (taxon non trouvé, erreur réseau sur la classification), un
    `fatal_error` est émis à la place du `result` — le code de statut HTTP reste 200 dans tous
    les cas puisqu'il est déjà envoyé au moment où le premier octet du flux part (voir
    `FatalErrorEvent`). Les erreurs de configuration qui ne dépendent d'aucun appel réseau (ex.
    module de classification inconnu) restent de vraies erreurs HTTP, levées par
    `_classification_candidates` avant l'ouverture du flux.
    """
    ensure_modules_registered()
    options = _options_from_request(req)
    off = set(req.off)
    trees = module_domain_trees(exclude=off)
    priorities = module_priorities(exclude=off)
    candidates = _classification_candidates(req, off, trees, priorities)

    async def event_stream() -> AsyncIterator[str]:
        started = time.monotonic()
        logs: list[str] = []
        warnings: list[str] = []

        classification_started = time.monotonic()
        results: dict[str, tuple[Struct | None, Exception | None]] = {}
        async for event in _run_classification_batch(candidates, req, options, results, classification_started):
            yield event

        fallback = _classification_network_fallback(req, off, trees, results)
        if fallback:
            async for event in _run_classification_batch(fallback, req, options, results, classification_started):
                yield event

        # Ordre des candidats déclarés, pas `results` (rempli via `as_completed`, donc en ordre
        # d'arrivée réseau) — sinon le départage par priorité de `_pick_classification_winner`
        # devient non déterministe d'un appel à l'autre en cas d'égalité de priorité.
        successes = [cid for cid, _ in candidates + fallback if results[cid][0] is not None]
        if not successes:
            if all(exc is not None for _, exc in results.values()):
                yield _sse(
                    FatalErrorEvent(
                        status_code=502,
                        detail=f"Modules de classification en erreur réseau : {', '.join(sorted(results))}.",
                    )
                )
            else:
                yield _sse(
                    FatalErrorEvent(
                        status_code=404,
                        detail=f"Taxon « {req.taxon} » non trouvé (classifications essayées : {', '.join(sorted(results))}).",
                    )
                )
            return

        classification_id, exclus_regne = _pick_classification_winner(
            req.domaine, successes, trees, priorities, results
        )
        logs.append(f"Classification : {classification_id}")
        warnings.extend(_avertissements_exclusion_regne(exclus_regne, results))
        struct = results[classification_id][0]

        applicable = modules_possibles(struct.domaine, trees) or []
        enrichment_ids = [
            m for m in applicable if m != classification_id and m not in off and get_module(m) is not None
        ]
        yield _sse(PlanEvent(classification_id=classification_id, modules=enrichment_ids))

        runner = EnrichmentRunner(struct, classification_id, applicable, off, options, priorities)
        async for module_event in runner.run():
            yield _sse(
                ModuleStatusEvent(
                    module_id=module_event.module_id,
                    role="enrichment",
                    status=module_event.status,
                    message=module_event.message,
                    duration_seconds=module_event.duration_seconds,
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
