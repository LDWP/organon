"""Request and response schemas of the JSON API.

`GenerateRequest` extends `GenerateOptions`, so one model serves as
API schema, CLI flags and web form fields.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from organon.core.config import GenerateOptions
from organon.core.db_inventory import DbInventory
from organon.core.models import (
    Basionym,
    DistributionEntry,
    KingdomInconsistency,
    RankInconsistency,
    RankName,
)


class GenerateRequest(GenerateOptions):
    """Generation request: the taxon plus the options."""

    taxon: str = Field(..., description="Le nom scientifique du taxon à traiter")


class ExternalLink(BaseModel):
    """A debug link attributed to the module that produced it."""

    module_id: str
    html: str


class ReferenceItem(BaseModel):
    """One taxonomic reference, attributed to its module.

    Structured counterpart of `GenerateResponse.references_wikitext`.
    """

    module_id: str
    wikitext: str
    # False if the module domain excludes the taxon kingdom; still
    # manually checkable, only the initial state changes.
    default_checked: bool = True


class RankLine(BaseModel):
    """A taxobox rank with its formatted wikitext line.

    Lets the frontend compare ranks across classifications.
    """

    rank: str
    name: str
    line: str


class GenerateResponse(BaseModel):
    """Result of one generation."""

    requested_taxon: str
    resolved_taxon: str
    # Rank of the taxon itself (`rank_lines` holds higher ranks only).
    # Needed to call `POST /api/v1/subtaxa-merge`.
    taxon_rank: str = ""
    used_classification: str
    used_domain: str
    kingdom: str = ""
    extinct: bool = False
    # IUCN conservation status code reported by GBIF; empty if absent.
    iucn_status: str = ""
    # IUCN criteria (`links["iucn"]["criterion"]`); may be empty.
    iucn_criterion: str = ""
    vernacular_names: list[str] = []
    # Module -> names whose source gave no usable language code
    # (`struct.vernacular[module]["und"]`). Never rendered; flagged
    # so the user can sort them.
    vernacular_names_without_language: dict[str, list[str]] = {}
    # `struct.other_names` merged across sources by status.
    other_names: dict[str, list[str]] = {}
    wikitext: str
    # The `{{ébauche}}` to `{{Taxobox fin}}` block, isolated so that it
    # can be swapped without regenerating the other sections.
    taxobox_wikitext: str
    # The sub-taxa section, isolated like `taxobox_wikitext`.
    subtaxa_wikitext: str = ""
    # `struct.subtaxa.items` unformatted, so the frontend can merge
    # several sources (`POST /api/v1/subtaxa-merge`).
    subtaxa: list[RankName] = []
    # Module that supplied `subtaxa`; empty without sub-taxa.
    subtaxa_source: str = ""
    # Code written in the Taxobox `classification=`.
    classification_taxobox: str = ""
    # `render_see_also` output, isolated to compare an article.
    see_also_wikitext: str = ""
    # Taxonomic references isolated from `wikitext`, excluding
    # `{{Autres projets}}`. Derived from `reference_items`; kept for
    # callers already using this block.
    references_wikitext: str = ""
    # One entry per reference line, so the frontend can toggle each.
    reference_items: list[ReferenceItem] = []
    # Taxobox completeness (ranks found), to recommend a source for
    # the "taxobox" facet.
    taxobox_completeness_score: int = 0
    # Sub-taxa completeness (taxa found), for the "taxons inférieurs"
    # facet. Synonyms and vernacular names count in neither score.
    subtaxa_completeness_score: int = 0
    rank_lines: list[RankLine] = []
    external_links: list[ExternalLink] = []
    # Module -> information categories it reported ("Classification",
    # "Auteur"…), derived from the populated `Struct` fields.
    data_found: dict[str, list[str]] = {}
    # Module -> raw author it reported, before the majority vote.
    # Lets the user force a source via `GenerateOptions.author_source`.
    author_candidates: dict[str, str] = {}
    # `struct.taxon.author` once the vote or the forced source has
    # decided, as plain text.
    consolidated_author: str = ""
    # Wikified `consolidated_author`, as put in `{{Taxobox taxon}}`.
    resolved_author: str = ""
    # `struct.synonyms.items`, if a module reported any.
    synonyms: list[RankName] = []
    # Source module of `synonyms`; empty if none.
    synonyms_source: str = ""
    # `struct.basionym`, if a module reported one.
    basionym: Basionym | None = None
    logs: list[str] = []
    warnings: list[str] = []
    elapsed_seconds: float
    truncated: dict[str, bool] = {}
    # Enrichment modules whose detected kingdom differs from the
    # retained one (possible cross-kingdom homonymy). Partial: absence
    # does not guarantee coherence.
    kingdom_inconsistencies: list[KingdomInconsistency] = []
    # Competing classification modules disagreeing on family, order
    # or status. Partial, like `kingdom_inconsistencies`.
    rank_inconsistencies: list[RankInconsistency] = []
    # `Struct.habitat` ("marin" or "terrestre"); empty if unknown.
    habitat: str = ""
    # Module -> sorted, deduplicated country names (certain and
    # uncertain merged).
    distribution: dict[str, list[str]] = {}
    # `struct.distribution` as is, to compare with an article.
    distribution_entries: dict[str, DistributionEntry] = {}
    # Module -> taxon id in its database (`struct.links[module]["id"]`).
    # Absent for modules carrying none (`externe`, unresolved `col`).
    external_ids: dict[str, str] = {}


class ModuleStatusEvent(BaseModel):
    """SSE event: progress of one module during a generation.

    "running" is sent before the module's network call, then exactly
    one terminal status ("found", "empty" or "error").
    """

    type: Literal["module_status"] = "module_status"
    module_id: str
    role: Literal["classification", "enrichment"]
    status: Literal["running", "found", "empty", "error"]
    # Error detail, only when status is "error".
    message: str | None = None
    # Time since "running"; absent while running.
    duration_seconds: float | None = None


class PlanEvent(BaseModel):
    """SSE event sent once after classification succeeds.

    Lists the enrichment modules to run, so the frontend can show every
    pending status row.
    """

    type: Literal["plan"] = "plan"
    classification_id: str
    modules: list[str]


class ResultEvent(BaseModel):
    """Last SSE event of a successful generation."""

    type: Literal["result"] = "result"
    data: GenerateResponse


class FatalErrorEvent(BaseModel):
    """SSE event for a generation that cannot complete.

    The SSE equivalent of an `HTTPException`: the HTTP status is
    already sent when the error occurs.
    """

    type: Literal["fatal_error"] = "fatal_error"
    status_code: int
    detail: str


class SearchMatch(BaseModel):
    """A taxon search suggestion.

    `gbif_key` and `parent_key` let the frontend rebuild a confirmed
    parentage between suggestions rather than guess from names.
    """

    scientific_name: str
    author: str = ""
    extinct: bool = False
    kingdom: str = ""
    rank: str = ""
    vernacular_names: list[str] = []
    source: str = "GBIF"
    gbif_key: int | None = None
    parent_key: int | None = None
    # Wikidata QID, only when the search was on a Wikidata item.
    qid: str | None = None
    # External ids of the Wikidata item (module id -> id), exposed but
    # not yet wired to id-based resolution.
    external_ids: dict[str, str] = {}


class SearchResponse(BaseModel):
    """Search suggestions for a query."""

    query: str
    matches: list[SearchMatch] = []


class ModuleInfo(BaseModel):
    """Public description of a registered module."""

    id: str
    can_classify: bool
    can_render_external_link: bool
    domains: str | list[str]
    priority: int
    is_default: bool


class DomainInfo(BaseModel):
    """A domain and its parent."""

    id: str
    parent: str | None = None


class VersionInfo(BaseModel):
    """API version."""

    version: str


class SourcesResponse(DbInventory):
    """Response of GET /api/v1/sources.

    An alias of `DbInventory`: no separate envelope needed.
    """


class CommonsImageSuggestion(BaseModel):
    """A Commons image proposed for the taxobox.

    Already filtered by license and quality or featured status.
    """

    file_name: str
    thumb_url: str
    page_url: str
    license_code: str
    license_label: str
    assessments: list[str] = []
    # True if the Wikidata item already uses this image (P18).
    is_wikidata_image: bool = False


class CommonsImagesResponse(BaseModel):
    """Commons image suggestions for a taxon."""

    taxon: str
    category_title: str
    search_url: str
    category_url: str | None = None
    suggestions: list[CommonsImageSuggestion] = []


class MergedSpeciesOut(BaseModel):
    """A merged sub-taxon, see `subtaxa_merge.MergedSpecies`."""

    name: str
    rank: str
    line: str
    default_checked: bool


class MergedGroupOut(BaseModel):
    """Species reported by the same sources, see `MergedGroup`."""

    sources: list[str]
    kind: Literal["primary", "alternative"]
    intro: str
    species: list[MergedSpeciesOut]


class MergedSubtaxaResponse(BaseModel):
    """Response of `POST /api/v1/subtaxa-merge`."""

    rank_text: str
    rank_text_singular: str
    pronoun: Literal["il", "elle"]
    taxon_phrase: str
    # (plural, singular) rank name per rank key, so the frontend can
    # recompute `rank_text` as boxes are checked.
    rank_names: dict[str, tuple[str, str]]
    groups: list[MergedGroupOut]


class SubtaxaMergeSource(BaseModel):
    """A source already resolved by the frontend.

    Merged locally with no extra network call.
    """

    module_id: str
    subtaxa: list[RankName] = Field(default_factory=list)


class SubtaxaMergeRequest(BaseModel):
    """Request to merge sub-taxa lists of several sources."""

    taxon_rank: str = Field(..., description="Rang du taxon principal (ex. 'genre', 'famille')")
    taxon_name: str = Field(..., description="Nom du taxon principal (ex. 'Panthera')")
    kingdom: str = ""
    sources: list[SubtaxaMergeSource] = Field(default_factory=list)


class TaxoboxRefreshRequest(BaseModel):
    """Request to write a full wikitext to a page."""

    page_title: str = Field(..., description="Titre de la page Wikipédia à éditer")
    wikitext: str = Field(
        ...,
        description="Wikitexte complet à écrire sur la page (ex. produit par /api/v1/generate)",
    )


class TaxoboxRefreshResponse(BaseModel):
    """Outcome of a taxobox refresh edit."""

    page_title: str
    new_revision_id: int
    requested_by: str


class UpdateDiagnoseRequest(BaseModel):
    """Request to diagnose a taxon against Wikidata and frwiki."""

    taxon: str | None = Field(None, description="Nom scientifique du taxon")
    qid: str | None = Field(None, description="QID Wikidata ; prime sur `taxon`")
    classification: str | None = Field(None, description="Module de classification de référence")
    domain: str = Field(
        "*", description="Domaine de la recherche : même génération que celle déjà affichée"
    )
    gbif_key: int | None = Field(None, description="Clé GBIF de la correspondance choisie")

    @model_validator(mode="after")
    def _taxon_ou_qid(self) -> UpdateDiagnoseRequest:
        if not (self.taxon or self.qid):
            raise ValueError("`taxon` ou `qid` est requis")
        return self


class UpdateExportRequest(BaseModel):
    """Request to export the checked proposals as QuickStatements."""

    qid: str | None = Field(
        None, description="QID Wikidata de l'item à mettre à jour (absent : création d'un item)"
    )
    taxon: str | None = Field(None, description="Nom scientifique du taxon")
    classification: str | None = Field(None, description="Module de classification de référence")
    domain: str = Field(
        "*", description="Domaine de la recherche : même génération que celle déjà affichée"
    )
    gbif_key: int | None = Field(None, description="Clé GBIF de la correspondance choisie")
    proposal_ids: list[str] = Field(
        ..., min_length=1, description="Ids des propositions cochées du diagnostic"
    )

    @model_validator(mode="after")
    def _qid_or_taxon(self) -> UpdateExportRequest:
        if not self.qid and not self.taxon:
            raise ValueError("`taxon` ou `qid` requis")
        return self


class UpdateExportResponse(BaseModel):
    """QuickStatements export of the checked proposals."""

    quickstatements: str
    retrieved: date
