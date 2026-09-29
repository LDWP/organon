"""Diagnosis of a published taxon.

Read its Wikidata item, run the Organon generation to get what the
sources say, then delegate the comparison to
`organon.core.update_diagnosis.diagnose`. Read-only: no Wikidata write,
no source value corrects another.

`generate` is injected (in practice `_generate_core`), so this module
does not depend on the API layer and tests need no network.

Deliberately not registered with `@register_module`: it takes no part in
the generation pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from organon.api.schemas import GenerateRequest, GenerateResponse
from organon.core.distribution_diagnosis import compare_distribution
from organon.core.distribution_parser import parse_repartition
from organon.core.subtaxa_diagnosis import compare_subtaxa
from organon.core.subtaxa_parser import parse_sous_taxons
from organon.core.taxobox_diagnosis import diagnose_taxobox, diagnose_uicn
from organon.core.taxobox_parser import parse_taxobox
from organon.core.update_diagnosis import (
    ArticleFrwiki,
    ContextePropositions,
    DiagnosticResponse,
    Ecart,
    IdentifiantWikidata,
    SectionFrwiki,
    SourceView,
    StatementSansReference,
    WikidataView,
    build_creation,
    build_synonym_creation,
    diagnose,
)
from organon.core.wikilinks_diagnosis import diagnose_liens
from organon.modules.wikidata.adapter import (
    DATABASE_ITEMS,
    EXTERNAL_ID_PROPERTIES,
    IUCN_STATUS_QIDS,
    RANK_QIDS,
    WikidataEntityAdapter,
)
from organon.modules.wikimedia.wikidata.adapter import WikidataSparqlAdapter
from organon.modules.wikimedia.wikipedia.adapter import WikipediaAdapter

logger = logging.getLogger(__name__)

# taxon, monotypic taxon, fossil taxon, clade; see
# docs/md/wikidata-conventions.md
TAXON_CLASSES = frozenset({"Q16521", "Q310890", "Q23038290", "Q713623"})
_REFERENCED_PROPERTIES = ("P225", "P171", "P1420")
_COMPARABLE_MODULES = frozenset(EXTERNAL_ID_PROPERTIES.values())
GBIF_COL_XR = "gbif_col_xr"
POWO_LSID_PREFIX = "urn:lsid:ipni.org:names:"

# Write property per module: P846 (legacy key) for `gbif`, P14607 for
# the COL XR id (see `build_wikidata_view`); the rest comes from
# EXTERNAL_ID_PROPERTIES, of which this is the inverse.
_ID_PROPERTIES: dict[str, IdentifiantWikidata] = {
    **{m: IdentifiantWikidata(propriete=p) for p, m in EXTERNAL_ID_PROPERTIES.items()},
    "gbif": IdentifiantWikidata(propriete="P846"),
    GBIF_COL_XR: IdentifiantWikidata(propriete="P14607"),
    "powo": IdentifiantWikidata(propriete="P5037", prefixe=POWO_LSID_PREFIX),
}
_RANK_QIDS_BY_NAME = {name: qid for qid, name in RANK_QIDS.items()}


class TaxonNotFoundError(Exception):
    """The item requested by QID does not exist."""


class AmbiguousTaxonError(Exception):
    """Several items bear this name: the user must choose."""

    def __init__(self, candidates: list[str]) -> None:
        """Keep the candidate QIDs."""
        super().__init__(", ".join(candidates))
        self.candidates = candidates


def build_source_view(resp: GenerateResponse) -> SourceView:
    """Reduce the generation response to what the comparator reads.

    The GBIF `id` is either the legacy key or the COL XR id (see
    `GbifModule._collect`): `gbif_key` (P846) and `id` (P14607, only if
    different from the key) are compared apart, never inferred from the
    format of `id` (a COL XR id may be all digits).
    """
    ids = {
        module_id: value
        for module_id, value in resp.external_ids.items()
        if module_id in _COMPARABLE_MODULES and module_id != "gbif"
    }
    gbif_key = resp.external_ids.get("gbif_key")
    if gbif_key:
        ids["gbif"] = gbif_key
        gbif_id = resp.external_ids.get("gbif")
        if gbif_id and gbif_id != gbif_key:
            ids[GBIF_COL_XR] = gbif_id
    return SourceView(
        source=resp.used_classification,
        name=resp.resolved_taxon,
        rank=resp.taxon_rank or None,
        parent_name=resp.rank_lines[0].name if resp.rank_lines else None,
        synonyms=[s.name for s in resp.synonyms],
        external_ids=ids,
        redirected_from=(
            resp.requested_taxon if resp.requested_taxon != resp.resolved_taxon else None
        ),
        uicn=resp.iucn_status or None,
    )


def _item_ids(adapter: WikidataEntityAdapter, entity: dict[str, Any], prop: str) -> list[str]:
    """Return the item ids targeted by the statements of `prop`."""
    return [
        s.value["id"]
        for s in adapter.statements(entity, prop)
        if isinstance(s.value, dict) and "id" in s.value
    ]


def _first_name(adapter: WikidataEntityAdapter, entity: dict[str, Any]) -> str | None:
    """Return the first scientific name (P225) of an entity, or None."""
    names = [s.value for s in adapter.statements(entity, "P225") if isinstance(s.value, str)]
    return names[0] if names else None


def build_wikidata_view(
    adapter: WikidataEntityAdapter,
    qid: str,
    entity: dict[str, Any],
    related: dict[str, dict[str, Any]],
) -> WikidataView:
    """Build the comparable view of an item.

    `related` holds the already fetched entities of parents and synonyms
    (P171, P1420).
    """
    external_ids = adapter.external_id_values(entity)
    # P5037 stores the full IPNI LSID, the POWO module only its number.
    if "powo" in external_ids:
        external_ids["powo"] = [v.removeprefix(POWO_LSID_PREFIX) for v in external_ids["powo"]]
    # P846 = legacy GBIF key; P14607 = COL XR id (see
    # docs/md/wikidata-conventions.md).
    for prop, key in (("P846", "gbif"), ("P14607", GBIF_COL_XR)):
        values = [s.value for s in adapter.statements(entity, prop) if isinstance(s.value, str)]
        if values:
            external_ids[key] = values
        else:
            external_ids.pop(key, None)
    return WikidataView(
        qid=qid,
        is_taxon=bool(set(_item_ids(adapter, entity, "P31")) & TAXON_CLASSES),
        names=[s.value for s in adapter.statements(entity, "P225") if isinstance(s.value, str)],
        rank=adapter.rank(entity),
        parent_names=_related_names(adapter, entity, "P171", related),
        synonyms=_related_names(adapter, entity, "P1420", related),
        external_ids=external_ids,
        unreferenced=_unreferenced(adapter, entity, related),
        uicn=_item_ids(adapter, entity, "P141"),
    )


def _unreferenced(
    adapter: WikidataEntityAdapter, entity: dict[str, Any], related: dict[str, dict[str, Any]]
) -> list[StatementSansReference]:
    """Return the statements of referenced properties lacking one."""
    found: list[StatementSansReference] = []
    for prop in _REFERENCED_PROPERTIES:
        for s in adapter.statements(entity, prop):
            if s.references:
                continue
            if isinstance(s.value, str):
                found.append(
                    StatementSansReference(
                        propriete=prop, valeur=s.value, type="chaine", nom=s.value
                    )
                )
            elif isinstance(s.value, dict) and "id" in s.value:
                target = s.value["id"]
                name = _first_name(adapter, related[target]) if target in related else None
                found.append(
                    StatementSansReference(
                        propriete=prop, valeur=target, type="item", nom=name or target
                    )
                )
    return found


def _related_names(
    adapter: WikidataEntityAdapter,
    entity: dict[str, Any],
    prop: str,
    related: dict[str, dict[str, Any]],
) -> list[str]:
    """Return the names of the related items targeted by `prop`."""
    names = (
        _first_name(adapter, related[qid])
        for qid in _item_ids(adapter, entity, prop)
        if qid in related
    )
    return [n for n in names if n]


def _section(section: Any, discrepancies: list[Ecart], **kw: Any) -> SectionFrwiki:
    """Build a frwiki section whose findings target frwiki."""
    return SectionFrwiki(
        section=section,
        ecarts=[e.model_copy(update={"cible": "frwiki"}) for e in discrepancies],
        **kw,
    )


def _frwiki_sections(content: str, resp: GenerateResponse) -> list[SectionFrwiki]:
    """Compare each zone of the article with what the generation says.

    A zone the source is silent on is not compared (no section).
    """
    taxobox = parse_taxobox(content)
    sections = [
        _section(
            "classification",
            diagnose_taxobox(
                taxobox,
                rank_lines=[(r.rank, r.name) for r in resp.rank_lines],
                taxon_nom=resp.resolved_taxon,
                taxon_rang=resp.taxon_rank or None,
                source=resp.classification_taxobox or resp.used_classification,
                redirected_from=(
                    resp.requested_taxon if resp.requested_taxon != resp.resolved_taxon else None
                ),
            ),
        )
    ]
    if resp.iucn_status:
        sections.append(
            _section(
                "uicn",
                diagnose_uicn(
                    taxobox,
                    risque=resp.iucn_status,
                    critere=resp.iucn_criterion or None,
                    source="iucn",
                ),
            )
        )
    if resp.see_also_wikitext:
        sections.append(
            _section(
                "liens",
                diagnose_liens(content, resp.see_also_wikitext, source="organon"),
            )
        )
    truncated = resp.truncated.get("subtaxa", False)
    if resp.subtaxa or truncated:
        view = parse_sous_taxons(content)
        subtaxa = compare_subtaxa(
            view.noms if view else None,
            [n.name for n in resp.subtaxa],
            source=resp.subtaxa_source,
            truncated=truncated,
        )
        sections.append(
            _section(
                "sous_taxons",
                subtaxa.ecarts,
                comptes=asdict(subtaxa.comptes) if subtaxa.comptes else None,
                limites=subtaxa.limites,
            )
        )
    if resp.distribution_entries:
        distribution = compare_distribution(parse_repartition(content), resp.distribution_entries)
        sections.append(
            _section(
                "repartition",
                distribution.ecarts,
                comptes=asdict(distribution.comptes) if distribution.comptes else None,
                niveau=distribution.niveau,
                limites=distribution.limites,
            )
        )
    return sections


async def _diagnose_frwiki(
    title: str | None, resp: GenerateResponse, wikipedia: WikipediaAdapter | None
) -> tuple[ArticleFrwiki | None, list[SectionFrwiki], list[str]]:
    """Diagnose the linked frwiki article; never raise.

    An outage or a missing page becomes a warning.
    """
    if title is None:
        absent = Ecart(
            type="article_absent_frwiki",
            severite="info",
            propriete="sitelink frwiki",
            source=resp.used_classification,
            message="Aucun article frwiki lié à l'item.",
        )
        return None, [_section("article", [absent])], []
    owned = WikipediaAdapter() if wikipedia is None else None
    reader = owned or wikipedia
    assert reader is not None
    try:
        page = await reader.wikitext(title)
    except httpx.HTTPError as exc:
        logger.warning("frwiki : article « %s » illisible (%s)", title, exc)
        return None, [], [f"Article frwiki illisible ({type(exc).__name__}) : non comparé."]
    finally:
        if owned is not None:
            await owned.aclose()
    if page is None:
        return None, [], [f"Article frwiki « {title} » introuvable : non comparé."]
    article = ArticleFrwiki(
        titre=page.title,
        revid=page.revid,
        date=page.timestamp,
        url="https://fr.wikipedia.org/wiki/" + quote(page.title.replace(" ", "_"), safe="_(),:'"),
    )
    return article, _frwiki_sections(page.content, resp), []


def _context(
    source: SourceView,
    resolved_items: Mapping[str, str | None],
    missing_names: frozenset[str] = frozenset(),
) -> ContextePropositions:
    """Build the context needed to make proposals."""
    return ContextePropositions(
        retrieved=date.today(),
        database_items=DATABASE_ITEMS,
        rank_qid=_RANK_QIDS_BY_NAME.get(source.rank or ""),
        resolved_items=resolved_items,
        id_properties=_ID_PROPERTIES,
        statut_qids=IUCN_STATUS_QIDS,
        noms_absents=missing_names,
    )


async def _diagnose_absent_synonym(
    taxon: str,
    source: SourceView,
    absent: Ecart,
    warnings: list[str],
    resolver: WikidataSparqlAdapter,
) -> DiagnosticResponse:
    """Diagnose a name the source treats as a synonym.

    The item is only created linked to the accepted taxon's item, if it
    exists and is unique. The source ids are those of the accepted
    taxon: no duplicate check by id.
    """
    creation = None
    try:
        accepted = (await resolver.taxon_qids([source.name])).get(source.name, [])
    except httpx.HTTPError as exc:
        logger.warning("Wikidata : taxon accepté de « %s » non résolu (%s)", taxon, exc)
        warnings.append(f"Taxon accepté non résolu ({type(exc).__name__}) : synonyme non proposé.")
    else:
        if len(accepted) == 1:
            creation = build_synonym_creation(taxon, accepted[0], source, _context(source, {}))
    discrepancy = (
        absent.model_copy(
            update={
                "severite": "suggestion",
                "source": source.source,
                "message": f"Synonyme de « {source.name} » : création proposée.",
                "creation": creation,
            }
        )
        if creation
        else absent
    )
    return DiagnosticResponse(
        qid=None,
        taxon=taxon,
        source_reference=source.source,
        ecarts=[discrepancy],
        avertissements=warnings,
    )


async def _diagnose_absent(
    taxon: str,
    classification: str | None,
    domain: str,
    gbif_key: int | None,
    generate: Callable[[GenerateRequest], Awaitable[GenerateResponse]],
    resolver: WikidataSparqlAdapter,
) -> DiagnosticResponse:
    """Diagnose a name with no item, proposing its creation.

    Not proposed if the source ignores it, if an external id finds it on
    another item (duplicate), or if the absence of a duplicate could not
    be checked. Never raise: any failure leaves the bare finding.
    """
    absent = Ecart(
        type="item_absent",
        severite="erreur",
        propriete="P225",
        valeur_source=taxon,
        source="wikidata",
        message="Aucun item Wikidata de taxon pour ce nom.",
    )

    def no_creation(*warnings: str) -> DiagnosticResponse:
        return DiagnosticResponse(
            qid=None, taxon=taxon, ecarts=[absent], avertissements=list(warnings)
        )

    try:
        resp = await generate(
            GenerateRequest(
                taxon=taxon,
                classification=classification or "",
                domain=domain,
                gbif_key=gbif_key,
            )
        )
    except httpx.HTTPError as exc:
        logger.warning("Wikidata : génération de « %s » impossible, réseau (%s)", taxon, exc)
        return no_creation(
            f"Création non proposée : génération impossible ({type(exc).__name__})."
        )
    except Exception as exc:  # boundary: a module bug yields no_creation
        logger.exception("Wikidata : génération de « %s » en échec, bug interne", taxon)
        return no_creation(
            f"Création non proposée : génération impossible ({type(exc).__name__})."
        )

    source = build_source_view(resp)
    warnings = list(resp.warnings)
    if source.redirected_from is not None:
        return await _diagnose_absent_synonym(taxon, source, absent, warnings, resolver)
    pairs = {
        _ID_PROPERTIES[m].propriete: _ID_PROPERTIES[m].prefixe + str(v)
        for m, v in source.external_ids.items()
        if m in _ID_PROPERTIES
    }
    try:
        duplicates = await resolver.items_by_external_ids(pairs)
    except httpx.HTTPError as exc:
        logger.warning("Wikidata : contrôle de doublon de « %s » impossible (%s)", taxon, exc)
        return no_creation(
            *warnings,
            f"Création non proposée : absence de doublon non vérifiée ({type(exc).__name__}).",
        )
    if duplicates:
        existing = ", ".join(duplicates)
        return DiagnosticResponse(
            qid=None,
            taxon=taxon,
            source_reference=source.source,
            ecarts=[
                Ecart(
                    type="item_doublon_possible",
                    severite="avertissement",
                    propriete="P225",
                    valeur_source=taxon,
                    source="wikidata",
                    message=f"Un identifiant externe de la source existe déjà sur : {existing}.",
                )
            ],
            avertissements=warnings,
        )

    resolved: dict[str, str | None] = {}
    if source.parent_name:
        try:
            found = await resolver.taxon_qids([source.parent_name])
            resolved = {n: q[0] if len(q) == 1 else None for n, q in found.items()}
        except httpx.HTTPError as exc:
            logger.warning("Wikidata : parent de « %s » non résolu (%s)", taxon, exc)
            warnings.append(f"Parent non résolu ({type(exc).__name__}) : omis de la création.")
    creation = build_creation(source, _context(source, resolved))
    discrepancy = (
        absent.model_copy(
            update={
                "severite": "suggestion",
                "source": source.source,
                "message": "Aucun item Wikidata : création proposée d'après la source.",
                "creation": creation,
            }
        )
        if creation
        else absent
    )
    return DiagnosticResponse(
        qid=None,
        taxon=taxon,
        source_reference=source.source,
        ecarts=[discrepancy],
        avertissements=warnings,
    )


async def diagnose_taxon(
    *,
    taxon: str | None,
    qid: str | None,
    classification: str | None,
    generate: Callable[[GenerateRequest], Awaitable[GenerateResponse]],
    domain: str = "*",
    gbif_key: int | None = None,
    wikidata: WikidataEntityAdapter | None = None,
    resolver: WikidataSparqlAdapter | None = None,
    resolved_items: Mapping[str, str | None] | None = None,
    wikipedia: WikipediaAdapter | None = None,
) -> DiagnosticResponse:
    """Diagnose a taxon; `qid` takes precedence over `taxon`.

    Raise `AmbiguousTaxonError` (homonyms) and `TaxonNotFoundError`
    (unknown QID); errors of `generate` and of Wikidata (httpx)
    propagate as is. A taxon merely absent from Wikidata is not an
    exception but an `item_absent` finding. `resolved_items` (name to
    target QID, None if absent or ambiguous) feeds the parent and
    synonym proposals; resolved here in one WDQS batch if not given.
    """
    if not qid and not taxon:
        raise ValueError("`taxon` ou `qid` requis")
    owned_wikidata, owned_resolver = wikidata is None, resolver is None
    wikidata = wikidata or WikidataEntityAdapter()
    resolver = resolver or WikidataSparqlAdapter()
    try:
        if qid:
            qid = qid.upper()
        else:
            assert taxon is not None
            found = await resolver.qids(taxon)
            if not found:
                return await _diagnose_absent(
                    taxon, classification, domain, gbif_key, generate, resolver
                )
            if len(found) > 1:
                raise AmbiguousTaxonError(found)
            qid = found[0]

        entity = await wikidata.get_entity(qid)
        if entity is None:
            raise TaxonNotFoundError(qid)
        name = taxon or _first_name(wikidata, entity)
        if not name:
            return DiagnosticResponse(
                qid=qid,
                taxon="",
                ecarts=[
                    Ecart(
                        type="nom_absent_wikidata",
                        severite="erreur",
                        propriete="P225",
                        source="wikidata",
                        message="L'item n'a pas de nom scientifique (P225).",
                    )
                ],
            )

        resp = await generate(
            GenerateRequest(
                taxon=name, classification=classification or "", domain=domain, gbif_key=gbif_key
            )
        )

        warnings = list(resp.warnings)
        related_ids = _item_ids(wikidata, entity, "P171") + _item_ids(wikidata, entity, "P1420")
        related: dict[str, dict[str, Any]] = {}
        source = build_source_view(resp)
        try:
            related = await wikidata.get_entities(related_ids) if related_ids else {}
        except httpx.HTTPError as exc:
            logger.warning("Wikidata : parents/synonymes de %s illisibles (%s)", qid, exc)
            warnings.append(
                "Parents et synonymes Wikidata illisibles (panne réseau) : non comparés."
            )
            source = source.model_copy(update={"parent_name": None, "synonyms": []})

        missing: frozenset[str] = frozenset()
        if resolved_items is None:
            resolved_items = {}
            names = [n for n in [source.parent_name, *source.synonyms] if n]
            try:
                resolved = await resolver.taxon_qids(names) if names else {}
                # 0 or several items: no arbitrary choice, the finding
                # stays informative.
                resolved_items = {n: q[0] if len(q) == 1 else None for n, q in resolved.items()}
                missing = frozenset(n for n, q in resolved.items() if not q)
            except httpx.HTTPError as exc:
                logger.warning("Wikidata : résolution des noms de %s impossible (%s)", qid, exc)
                warnings.append(
                    "Résolution des items parent/synonymes impossible "
                    f"({type(exc).__name__}) : aucune proposition."
                )

        article_frwiki, sections_frwiki, frwiki_warnings = await _diagnose_frwiki(
            wikidata.frwiki_title(entity), resp, wikipedia
        )
        warnings.extend(frwiki_warnings)

        wd_view = build_wikidata_view(wikidata, qid, entity, related)
        return DiagnosticResponse(
            qid=qid,
            taxon=name,
            source_reference=source.source,
            ecarts=diagnose(
                wd_view,
                source,
                _context(source, resolved_items, missing),
            ),
            article_frwiki=article_frwiki,
            sections_frwiki=sections_frwiki,
            avertissements=warnings,
        )
    finally:
        if owned_wikidata:
            await wikidata.aclose()
        if owned_resolver:
            await resolver.aclose()
