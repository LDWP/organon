"""POST /api/v1/generate: the generation orchestration.

Resolves and runs the classification, runs the enrichment modules
applicable to the domain, computes categories and portals, resolves
the main author, then renders the wikitext.

The author is resolved here rather than at rendering because it
needs `struct.regne` to pick the right table; its disagreement
warnings join the module warnings in the response.

POST /api/v1/generate/stream runs the same pipeline as Server-Sent
Events: one `module_status` per module, a `plan` once the
classification is known, then a final `result` identical to the
`/generate` body. `EnrichmentRunner` is shared by both endpoints.

Both endpoints, and `POST /update/diagnose` and `/update/export`
through `_generate_core`, share one computation; see
`_generation_cache`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from organon.api.deps import require_username
from organon.api.generation_cache import GenerationCache
from organon.api.rate_limit import limiter
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
from organon.core.domains import DomainTree, best_classification, possible_modules
from organon.core.langues import LANGUE_INDETERMINEE
from organon.core.models import FOOTER_LINK, Struct, TaxonInfo
from organon.core.registry import (
    TaxonomyModule,
    classification_modules,
    default_classification_module,
    get_module,
    module_domain_trees,
    module_priorities,
)
from organon.core.rendering.authors import resolve_main_author, unknown_botanist_tokens
from organon.core.rendering.engine import (
    render,
    render_references_items_block,
    render_subtaxa_block,
    render_taxobox_block,
)
from organon.core.rendering.sections import compute_rank_lines, render_see_also
from organon.core.rendering.support import add_if_needed, country_data_by_code
from organon.core.selectors.categorization import compute_footer_links
from organon.core.selectors.coherence import (
    consistent_kingdom_classifications,
    detect_kingdom_inconsistencies,
    detect_rank_inconsistencies,
    gbif_probable_year_validated,
    reference_module_is_consistent,
)
from organon.core.wikidata_authors import lookup_author_qids

router = APIRouter()

# Shared by POST /generate, GET /generate and POST /generate/stream:
# three ways to trigger the same costly operation (~20 external calls,
# 10-20s). One search already triggers up to ~8 of them (App.jsx
# prefetchOtherClassifications, one per applicable classification
# module).
_GENERATE_RATE_LIMIT = "40/minute"
logger = logging.getLogger(__name__)

# Per-module namespaced fields, plus `domain`, which only the request
# decides.
_UNMERGED_FIELDS = frozenset(
    {"links", "vernacular", "other_names", "description", "distribution", "domain"}
)
# Single-value `Struct` fields several enrichment modules may write.
# A module changed one only if its value differs from the
# pre-enrichment baseline; see `EnrichmentRunner.run` for the merge.
_MONOVALUE_FIELDS = tuple(f for f in Struct.model_fields if f not in _UNMERGED_FIELDS)

# Per-attempt bound (s) when `options.timeout` is 0, so one slow
# parallel module cannot block the whole search.
_CLASSIFICATION_FALLBACK_TIMEOUT = 20.0


async def _collect_with_timeout(
    module: TaxonomyModule,
    struct: Struct,
    *,
    is_classification: bool,
    options: GenerateOptions,
    fallback_timeout: float | None = None,
) -> Struct | None:
    """Run `module.collect` under `options.timeout` or the fallback.

    The only place that reads `GenerateOptions.timeout`.
    """
    coro = module.collect(struct, is_classification=is_classification, options=options)
    timeout = options.timeout if options.timeout > 0 else fallback_timeout
    if timeout:
        return await asyncio.wait_for(coro, timeout=timeout)
    return await coro


def _log_module_failure(module_id: str, role: str, exc: Exception) -> None:
    """Log a module failure.

    A network error or timeout is expected (warning); any other
    exception is a module bug, logged with its traceback.
    """
    if isinstance(exc, httpx.HTTPError | asyncio.TimeoutError):
        logger.warning("Module '%s' (%s) : erreur réseau (%s), ignoré.", module_id, role, exc)
    else:
        logger.exception("Module '%s' (%s) : erreur interne du module, ignoré.", module_id, role)


def _options_from_request(req: GenerateRequest) -> GenerateOptions:
    """Extract the generation options from a request."""
    return GenerateOptions(**req.model_dump(exclude={"taxon"}))


def _all_applicable_classification_modules(
    domain: str, off: set[str], trees: dict[str, DomainTree]
) -> list[tuple[str, TaxonomyModule]]:
    """Return the enabled classification modules covering `domaine`."""
    applicable = set(possible_modules(domain, trees) or [])
    candidates = [
        (m, get_module(m)) for m in classification_modules() if m in applicable and m not in off
    ]
    return [(m, module) for m, module in candidates if module is not None]


def _classification_candidates(
    req: GenerateRequest, off: set[str], trees: dict[str, DomainTree]
) -> list[tuple[str, TaxonomyModule]]:
    """Return the classification modules to query in parallel.

    An explicit choice (`req.classification`) gives a single candidate;
    see `_classification_network_fallback`. Otherwise all modules
    applicable to the domain, none favored; see
    `_pick_classification_winner`.
    """
    if req.classification:
        module = get_module(req.classification)
        if module is None or req.classification in off:
            raise HTTPException(
                400,
                detail=f"Module de classification '{req.classification}' inconnu ou désactivé.",
            )
        return [(req.classification, module)]

    candidates = _all_applicable_classification_modules(req.domain, off, trees)
    if not candidates:
        raise HTTPException(400, detail="Aucun module de classification disponible.")
    return candidates


def _classification_network_fallback(
    req: GenerateRequest, off: set[str], trees: dict[str, DomainTree], tried: dict[str, tuple]
) -> list[tuple[str, TaxonomyModule]]:
    """Return the other modules to retry after a network failure.

    An explicit choice failing on the network says nothing about the
    taxon. A "not found" is reliable and kept as is.
    """
    if not (req.classification and all(exc is not None for _, exc in tried.values())):
        return []
    return [
        (m, module)
        for m, module in _all_applicable_classification_modules(req.domain, off, trees)
        if m not in tried
    ]


async def _attempt_classification(
    module_id: str, module: TaxonomyModule, req: GenerateRequest, options: GenerateOptions
) -> tuple[str, Struct | None, Exception | None]:
    """Run one classification attempt; never raise.

    The result carries the error, so it cannot escape `gather` or
    `as_completed`.
    """
    struct = Struct(
        taxon=TaxonInfo(name=req.taxon), classification=req.classification, domain=req.domain
    )
    try:
        resolved = await _collect_with_timeout(
            module,
            struct,
            is_classification=True,
            options=options,
            fallback_timeout=_CLASSIFICATION_FALLBACK_TIMEOUT,
        )
        return module_id, resolved, None
    except Exception as exc:  # noqa: BLE001 - degraded to an HTTPException by the caller
        _log_module_failure(module_id, "classification", exc)
        return module_id, None, exc


async def _run_classification_batch(
    batch: list[tuple[str, TaxonomyModule]],
    req: GenerateRequest,
    options: GenerateOptions,
    results: dict[str, tuple[Struct | None, Exception | None]],
    started: float,
) -> AsyncIterator[ModuleStatusEvent]:
    """Run classification candidates in parallel, yielding progress.

    Each result is written to `results` as it arrives. Shared by the
    initial batch and the network fallback.
    """
    for cid, _ in batch:
        yield ModuleStatusEvent(module_id=cid, role="classification", status="running")
    tasks = [
        asyncio.create_task(_attempt_classification(cid, cm, req, options)) for cid, cm in batch
    ]
    for task in asyncio.as_completed(tasks):
        module_id, resolved, exc = await task
        results[module_id] = (resolved, exc)
        status: _ModuleStatus
        message: str | None
        if exc is not None:
            status, message = "error", str(exc)
        elif resolved is None:
            status, message = "error", "taxon non trouvé"
        else:
            status, message = "found", None
        yield ModuleStatusEvent(
            module_id=module_id,
            role="classification",
            status=status,
            message=message,
            duration_seconds=time.monotonic() - started,
        )


def _pick_classification_winner(
    domain: str,
    successes: list[str],
    trees: dict[str, DomainTree],
    priorities: dict[str, int],
    results: dict[str, tuple[Struct | None, Exception | None]],
) -> tuple[str, list[str]]:
    """Pick the winning classification among the successful modules.

    Return (winner, excluded). First drop candidates whose kingdom is
    a minority (`consistent_kingdom_classifications`): a cross-kingdom
    homonym must not win on specialization or priority. The excluded
    are returned so the caller can report them. Without a domain
    filter, the majority kingdom serves as the domain, so a
    specialized module (LPSN, POWO) beats a better-ranked generalist.
    """
    kingdoms = {
        cid: struct.kingdom for cid in successes if (struct := results[cid][0]) is not None
    }
    consistent, excluded, majority_kingdom = consistent_kingdom_classifications(
        successes, kingdoms
    )
    pool = consistent or successes

    if domain == "*" and majority_kingdom:
        domain = majority_kingdom

    if len(pool) == 1 or domain == "*":
        return max(pool, key=lambda m: priorities.get(m, 0)), excluded
    # `best_classification` may return None (no positively scored module
    # and no registered default). Unlikely, but falling back to the
    # first candidate of `pool` (non-empty, `len(pool) >= 2`) beats
    # crashing.
    winner = (
        best_classification(
            domain,
            classification_module_ids=pool,
            module_trees=trees,
            module_priorities=priorities,
            default_module=default_classification_module(),
        )
        or pool[0]
    )
    return winner, excluded


def _kingdom_exclusion_warnings(
    excluded: list[str], results: dict[str, tuple[Struct | None, Exception | None]]
) -> list[str]:
    """Return a warning for each candidate dropped for its kingdom.

    They found something (e.g. a bacterial homonym of a fungus genus),
    so they must not vanish silently.
    """
    return [
        f"{cid.upper()} écarté de la classification : règne « {struct.kingdom} » "
        "minoritaire face aux autres sources (possible homonyme inter-règnes)."
        for cid in excluded
        if (struct := results[cid][0]) is not None
    ]


_ModuleStatus = Literal["running", "found", "empty", "error"]


@dataclass
class ModuleRunEvent:
    """Progress step of one module in `EnrichmentRunner.run`."""

    module_id: str
    status: _ModuleStatus
    message: str | None = None
    duration_seconds: float | None = None


class EnrichmentRunner:
    """Run the applicable enrichment modules in parallel.

    Accumulates `struct`, `ran_modules` and `warnings`. Extracted so
    `/generate/stream` can observe one `ModuleRunEvent` per module
    without duplicating the logic. See `run` for the merge order.
    """

    def __init__(
        self,
        struct: Struct,
        classification_id: str,
        applicable: list[str],
        off: set[str],
        options: GenerateOptions,
        priorities: dict[str, int],
    ) -> None:
        """Select the modules to run, lowest priority first."""
        self.struct = struct
        # Pre-enrichment snapshot, to tell a field written by a module
        # from an unchanged one (see `_MONOVALUE_FIELDS`).
        self._baseline = struct.model_copy(deep=True)
        self.ran_modules: list[str] = [classification_id]
        self._options = options
        # Filtered once here (classification handled separately,
        # disabled or unknown modules) so only queried modules get a
        # task and a "running" event. Sorted by increasing priority:
        # `run` applies results in that order, so the highest priority
        # wins on single-value fields (see `_MONOVALUE_FIELDS`).
        candidates = [
            m
            for m in applicable
            if m != classification_id and m not in off and get_module(m) is not None
        ]
        self.enrichment_ids = sorted(candidates, key=lambda m: priorities.get(m, 0))

    async def collect_one_module(
        self, module_id: str
    ) -> tuple[str, Struct | None, Exception | None]:
        """Run one module on its own copy of the struct; never raise.

        The result carries the error, so `run` can tell which module
        failed (`as_completed` does not preserve task identity). Each
        module gets a deep copy because modules mutate `struct` in
        place; `run` merges the copies in priority order.
        """
        module = get_module(module_id)
        assert module is not None  # guaranteed by the `enrichment_ids` filter
        try:
            updated = await _collect_with_timeout(
                module,
                self.struct.model_copy(deep=True),
                is_classification=False,
                options=self._options,
            )
            return module_id, updated, None
        except Exception as exc:  # noqa: BLE001 - a failing third-party module must not break the generation
            _log_module_failure(module_id, "enrichissement", exc)
            return module_id, None, exc

    async def run(self) -> AsyncIterator[ModuleRunEvent]:
        """Run all modules in parallel, yielding progress.

        Results are applied only once all finished, in `enrichment_ids`
        priority order, not arrival order, so single-value fields do not
        depend on latency. Namespaced fields merge with `update()`. Each
        `_MONOVALUE_FIELDS` entry is compared to `_baseline`.
        """
        started: dict[str, float] = {
            module_id: time.monotonic() for module_id in self.enrichment_ids
        }
        tasks = [
            asyncio.create_task(self.collect_one_module(module_id), name=module_id)
            for module_id in self.enrichment_ids
        ]
        for module_id in self.enrichment_ids:
            yield ModuleRunEvent(module_id, "running")

        results: dict[str, Struct] = {}
        for task in asyncio.as_completed(tasks):
            module_id, updated, exc = await task
            duration = time.monotonic() - started[module_id]
            if exc is not None:
                yield ModuleRunEvent(
                    module_id, "error", message=str(exc), duration_seconds=duration
                )
            elif updated is not None:
                results[module_id] = updated
                yield ModuleRunEvent(module_id, "found", duration_seconds=duration)
            else:
                # No warning: most modules cover a narrow domain, so
                # finding nothing is the common case, not an anomaly.
                # The "empty" status stays visible per module in the
                # frontend.
                yield ModuleRunEvent(module_id, "empty", duration_seconds=duration)

        for module_id in self.enrichment_ids:
            if module_id not in results:
                continue
            copy = results[module_id]
            self.struct.links.update(copy.links)
            self.struct.vernacular.update(copy.vernacular)
            self.struct.other_names.update(copy.other_names)
            self.struct.description.update(copy.description)
            self.struct.distribution.update(copy.distribution)
            for field in _MONOVALUE_FIELDS:
                value = getattr(copy, field)
                if value != getattr(self._baseline, field):
                    setattr(self.struct, field, value)
            self.ran_modules.append(module_id)


GenerationEvent = ModuleStatusEvent | PlanEvent | ResultEvent | FatalErrorEvent


def _keep_generation(events: list[GenerationEvent]) -> bool:
    """Keep only a generation that ran to completion.

    A `fatal_error` (source down, taxon not found) may be transient.
    """
    return bool(events) and isinstance(events[-1], ResultEvent)


_generation_cache: GenerationCache[GenerationEvent] = GenerationCache(keep=_keep_generation)


def _cache_key(req: GenerateRequest) -> str:
    """Return the cache key of a request."""
    return req.model_copy(update={"taxon": req.taxon.strip()}).model_dump_json()


def _cached_generation(req: GenerateRequest) -> AsyncIterator[GenerationEvent]:
    """Return the events of a request, computed once.

    Configuration errors (unknown module) are raised here, before any
    task starts.
    """
    off = set(req.off)
    candidates = _classification_candidates(req, off, module_domain_trees(exclude=off))
    return _generation_cache.stream(_cache_key(req), lambda: _generation_pipeline(req, candidates))


async def _generation_pipeline(
    req: GenerateRequest, candidates: list[tuple[str, TaxonomyModule]]
) -> AsyncIterator[GenerationEvent]:
    """Run the full pipeline shared by both endpoints.

    Yield a `module_status` per module, a `plan` after classification,
    then a `result`, or a `fatal_error` (taxon not found, network
    error on every classification module).
    """
    options = _options_from_request(req)
    off = set(req.off)
    trees = module_domain_trees(exclude=off)
    priorities = module_priorities(exclude=off)
    started = time.monotonic()
    logs: list[str] = []
    warnings: list[str] = []

    classification_started = time.monotonic()
    results: dict[str, tuple[Struct | None, Exception | None]] = {}
    async for event in _run_classification_batch(
        candidates, req, options, results, classification_started
    ):
        yield event

    fallback = _classification_network_fallback(req, off, trees, results)
    if fallback:
        async for event in _run_classification_batch(
            fallback, req, options, results, classification_started
        ):
            yield event

    # Declared candidate order, not `results` (filled in network arrival
    # order), so the priority tie-break stays deterministic.
    successes = [cid for cid, _ in candidates + fallback if results[cid][0] is not None]
    if not successes:
        if all(exc is not None for _, exc in results.values()):
            yield FatalErrorEvent(
                status_code=502,
                detail=(
                    f"Modules de classification en erreur réseau : {', '.join(sorted(results))}."
                ),
            )
        else:
            yield FatalErrorEvent(
                status_code=404,
                detail=(
                    f"Taxon « {req.taxon} » non trouvé "
                    f"(classifications essayées : {', '.join(sorted(results))})."
                ),
            )
        return

    classification_id, excluded_kingdom = _pick_classification_winner(
        req.domain, successes, trees, priorities, results
    )
    logs.append(f"Classification : {classification_id}")
    warnings.extend(_kingdom_exclusion_warnings(excluded_kingdom, results))
    struct = results[classification_id][0]
    assert struct is not None  # garanti par `successes` (voir _pick_classification_winner)

    applicable = possible_modules(struct.domain, trees) or []
    runner = EnrichmentRunner(struct, classification_id, applicable, off, options, priorities)
    yield PlanEvent(classification_id=classification_id, modules=runner.enrichment_ids)

    async for module_event in runner.run():
        yield ModuleStatusEvent(
            module_id=module_event.module_id,
            role="enrichment",
            status=module_event.status,
            message=module_event.message,
            duration_seconds=module_event.duration_seconds,
        )

    author_candidates = _select_main_author(runner.struct, options, classification_id)
    wikidata_authors = await lookup_author_qids(unknown_botanist_tokens(runner.struct))
    yield ResultEvent(
        data=_assemble_response(
            req,
            options,
            classification_id,
            runner.struct,
            runner.ran_modules,
            warnings,
            logs,
            started,
            author_candidates,
            wikidata_authors,
        )
    )


async def _generate_core(req: GenerateRequest) -> GenerateResponse:
    """Run a generation and return its response, raising HTTP errors."""
    result: GenerateResponse | None = None
    async for event in _cached_generation(req):
        if isinstance(event, FatalErrorEvent):
            raise HTTPException(event.status_code, detail=event.detail)
        if isinstance(event, ResultEvent):
            result = event.data
    assert (
        result is not None
    )  # le pipeline se termine toujours par un `result` ou un `fatal_error`
    # Copy: the cached response is shared and the caller may mutate it.
    return result.model_copy(deep=True)


@router.post("/generate", response_model=GenerateResponse)
@limiter.shared_limit(_GENERATE_RATE_LIMIT, scope="generate")
async def generate(
    request: Request, req: GenerateRequest, username: str = Depends(require_username)
) -> GenerateResponse:
    """Generate the article skeleton of a taxon."""
    return await _generate_core(req)


@router.get("/generate", response_model=GenerateResponse)
@limiter.shared_limit(_GENERATE_RATE_LIMIT, scope="generate")
async def generate_via_get(
    request: Request, taxon: str, username: str = Depends(require_username)
) -> GenerateResponse:
    """GET alias of `POST /generate`, with defaults except `taxon`.

    Lets a link or address bar trigger a generation. The frontend uses
    the POST endpoints, which expose all of `GenerateOptions`.
    """
    return await _generate_core(GenerateRequest(taxon=taxon))


def _author_candidates(struct: Struct, classification_id: str) -> dict[str, str]:
    """Return the raw author reported by each contributing module.

    Exposed so the user can force a source via
    `GenerateOptions.author_source` instead of the majority vote.
    """
    candidates: dict[str, str] = {}
    classification_author = (struct.taxon.author or "").strip()
    if classification_author:
        candidates[classification_id] = classification_author
    for module_id, data in struct.links.items():
        author = data.get("author")
        if author:
            candidates[module_id] = author.strip()
    return candidates


def _majority_author(candidates: dict[str, str], struct: Struct, classification_id: str) -> str:
    """Return the author most modules report identically.

    Better than the classification module's alone, which may have
    none. On a tie the classification author wins, else the first seen.
    """
    classification_author = (struct.taxon.author or "").strip()
    votes = [classification_author] if classification_author else []
    votes += [a for m, a in candidates.items() if m != classification_id]
    return Counter(votes).most_common(1)[0][0] if votes else ""


def _compute_data_found(struct: Struct, classification_id: str) -> dict[str, list[str]]:
    """Return, per module, the information categories it reported.

    Derived from the populated `struct` fields, not maintained by hand.
    """
    found: dict[str, list[str]] = {classification_id: ["Classification"]}

    def add(module_id: str | None, label: str) -> None:
        if not module_id:
            return
        labels = found.setdefault(module_id, [])
        if label not in labels:
            labels.append(label)

    if struct.subtaxa and struct.subtaxa.items:
        add(struct.subtaxa.source, "Taxons inférieurs")
    if struct.synonyms and struct.synonyms.items:
        add(struct.synonyms.source, "Synonymes")
    if struct.basionym:
        add(struct.basionym.source, "Basionyme")
    if struct.type_taxon:
        add(struct.type_taxon.source, "Taxon type")
    if struct.etymology:
        add(struct.etymology.source, "Étymologie")
    for module_id, entry in struct.distribution.items():
        if entry.certain or entry.uncertain:
            add(module_id, "Répartition")
    for module_id, names in struct.vernacular_names("fr").items():
        if names:
            add(module_id, "Noms vernaculaires")
    for module_id, data in struct.links.items():
        if data.get("author"):
            add(module_id, "Auteur")

    return found


def _compute_external_ids(struct: Struct, ran_modules: list[str]) -> dict[str, str]:
    """Return the taxon id of each contributing module.

    Follows the `struct.liens[module_id]['id']` convention; modules
    without it are absent.
    """
    ids: dict[str, str] = {}
    for module_id in ran_modules:
        data = struct.links.get(module_id, {})
        if data.get("id"):
            ids[module_id] = str(data["id"])
        if module_id == "gbif" and data.get("key"):
            ids["gbif_key"] = str(data["key"])
    return ids


def _extinct_fallback(struct: Struct) -> None:
    """Fall back to another module's extinction signal.

    Only if the classification source has none (None). An explicit
    False from it is kept; only an explicit True elsewhere counts.
    """
    if struct.taxon.extinct is not None:
        return
    if any(entry.get("extinct") for entry in struct.links.values()):
        struct.taxon.extinct = True


def _select_main_author(
    struct: Struct, options: GenerateOptions, classification_id: str
) -> dict[str, str]:
    """Set the retained author on `struct`; return the candidates.

    Not idempotent (the classification author is one of the candidates):
    call once, before `_assemble_response`.
    """
    author_candidates = _author_candidates(struct, classification_id)
    if options.author_source and options.author_source in author_candidates:
        struct.taxon.author = author_candidates[options.author_source]
    else:
        struct.taxon.author = _majority_author(author_candidates, struct, classification_id)
    # GBIF year (parsed from free-text `publishedIn`): added only if
    # another module reports it in its own author, never on parsing
    # alone.
    gbif_validated_year = gbif_probable_year_validated(struct, struct.taxon.author)
    if gbif_validated_year is not None:
        struct.taxon.author = f"{struct.taxon.author}, {gbif_validated_year}"
    return author_candidates


def _assemble_response(
    req: GenerateRequest,
    options: GenerateOptions,
    classification_id: str,
    struct: Struct,
    ran_modules: list[str],
    warnings: list[str],
    logs: list[str],
    started: float,
    author_candidates: dict[str, str],
    wikidata_authors: Mapping[str, str] | None = None,
) -> GenerateResponse:
    """Run the final steps shared by both endpoints.

    Kingdom inconsistencies, categories and portals, main author
    wikification, wikitext, external links and response. Local
    computation only, no network call: the author is already selected
    (`_select_main_author`) and Wikidata already queried.
    """
    _extinct_fallback(struct)
    kingdom_inconsistencies = detect_kingdom_inconsistencies(struct, classification_id)
    rank_inconsistencies = detect_rank_inconsistencies(struct, classification_id)

    struct.links[FOOTER_LINK] = compute_footer_links(struct, options)

    struct.taxon.resolved_author, author_warnings = resolve_main_author(struct, wikidata_authors)
    warnings = warnings + author_warnings

    wikitext = render(struct, options, ext_only=req.external_only)
    taxobox_wikitext = "" if req.external_only else render_taxobox_block(struct, options)
    subtaxa_wikitext = "" if req.external_only else render_subtaxa_block(struct, options)
    reference_items = [
        ReferenceItem(
            module_id=module_id,
            wikitext=wikitext,
            default_checked=reference_module_is_consistent(module_id, struct.kingdom),
        )
        for module_id, wikitext in render_references_items_block(struct)
    ]
    references_wikitext = (
        "\n".join(f"* {item.wikitext}" for item in reference_items) + "\n"
        if reference_items
        else ""
    )
    rank_lines = (
        []
        if req.external_only
        else [RankLine(rank=r, name=n, line=line) for r, n, line in compute_rank_lines(struct)]
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
        "subtaxa": bool(struct.subtaxa and struct.subtaxa.truncated),
        "synonyms": bool(struct.synonyms and struct.synonyms.truncated),
    }

    vernacular_merged: dict[str, list[str]] = {}
    for src, names in struct.vernacular_names("fr").items():
        for name in names:
            add_if_needed(vernacular_merged, name, src)

    other_names_merged: dict[str, dict[str, list[str]]] = {}
    for src, statuses in struct.other_names.items():
        for status, names in statuses.items():
            bucket = other_names_merged.setdefault(status, {})
            for name in names:
                add_if_needed(bucket, name, src)
    other_names_response = {status: list(names) for status, names in other_names_merged.items()}

    # Two independent measures, one per classification "zoom" facet
    # (taxobox, sub-taxa), so the frontend can recommend a different
    # source for each. Synonyms and vernacular names count in neither.
    taxobox_completeness_score = len(struct.ranks)
    subtaxa_completeness_score = len(struct.subtaxa.items if struct.subtaxa else [])

    data_found = _compute_data_found(struct, classification_id)

    distribution_merged: dict[str, list[str]] = {}
    for module_id, entry in struct.distribution.items():
        codes = {**entry.certain, **entry.uncertain}
        names = sorted(dict.fromkeys(country_data_by_code(code) for code in codes))
        if names:
            distribution_merged[module_id] = names

    return GenerateResponse(
        requested_taxon=req.taxon,
        resolved_taxon=struct.taxon.name,
        taxon_rank=struct.taxon.rank or "",
        used_classification=classification_id,
        used_domain=struct.domain,
        kingdom=struct.kingdom,
        extinct=bool(struct.taxon.extinct),
        iucn_status=struct.links.get("iucn", {}).get("risk", ""),
        iucn_criterion=struct.links.get("iucn", {}).get("criterion", ""),
        vernacular_names=list(vernacular_merged)[:6],
        vernacular_names_without_language=struct.vernacular_names(LANGUE_INDETERMINEE),
        other_names=other_names_response,
        wikitext=wikitext,
        taxobox_wikitext=taxobox_wikitext,
        subtaxa_wikitext=subtaxa_wikitext,
        subtaxa=struct.subtaxa.items if struct.subtaxa else [],
        subtaxa_source=(struct.subtaxa.source or "") if struct.subtaxa else "",
        classification_taxobox=struct.classification_taxobox,
        see_also_wikitext=render_see_also(struct, options),
        distribution_entries=struct.distribution,
        references_wikitext=references_wikitext,
        reference_items=reference_items,
        taxobox_completeness_score=taxobox_completeness_score,
        subtaxa_completeness_score=subtaxa_completeness_score,
        rank_lines=rank_lines,
        external_links=external_links,
        data_found=data_found,
        author_candidates=author_candidates,
        consolidated_author=struct.taxon.author or "",
        resolved_author=struct.taxon.resolved_author or "",
        synonyms=struct.synonyms.items if struct.synonyms else [],
        synonyms_source=(struct.synonyms.source or "") if struct.synonyms else "",
        basionym=struct.basionym,
        logs=logs,
        warnings=warnings,
        elapsed_seconds=round(time.monotonic() - started, 3),
        truncated=truncated,
        kingdom_inconsistencies=kingdom_inconsistencies,
        rank_inconsistencies=rank_inconsistencies,
        habitat=struct.habitat or "",
        distribution=distribution_merged,
        external_ids=_compute_external_ids(struct, ran_modules),
    )


def _sse(event: BaseModel) -> str:
    """Encode an event as Server-Sent Events.

    Format: a `data: <json>` line followed by a blank line.

    Going through Pydantic models guarantees the documented schema.
    `ensure_ascii` stays True so a proxy cannot split a multi-byte
    character.
    """
    return f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"


@router.post("/generate/stream")
@limiter.shared_limit(_GENERATE_RATE_LIMIT, scope="generate")
async def generate_stream(
    request: Request, req: GenerateRequest, username: str = Depends(require_username)
) -> StreamingResponse:
    """Stream a generation as Server-Sent Events.

    After the stream starts, failures become a `fatal_error` event and
    the HTTP status stays 200. Configuration errors are raised by
    `_classification_candidates` before the stream opens.
    """
    events = _cached_generation(req)

    async def event_stream() -> AsyncIterator[str]:
        async for event in events:
            yield _sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # Stops a proxy (e.g. nginx) from buffering the whole
            # response, which would defeat the stream.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
