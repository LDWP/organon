"""Typed state accumulated while generating one article.

Pydantic rejects malformed data at collection time. The keys of
`links` are fixed by `LinkEntry`: a misspelled name is a type
error, not a silent `None`.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict


class _Model(BaseModel):
    """Base model: unknown fields raise instead of being ignored.

    An obsolete or misspelled field name must fail loudly.
    """

    model_config = ConfigDict(extra="forbid")


# Key of `Struct.links` for the footer pseudo-module (portals and
# categories), written by the generation, not a `organon.modules`
# module; see `compute_footer_links`.
FOOTER_LINK: Final = "footer"


class _LinkDict(TypedDict, total=False):
    """Base of the `Struct.links` dicts.

    Unknown keys raise when `Struct` is built.
    """

    __pydantic_config__ = ConfigDict(extra="forbid")  # type: ignore[misc]


class ColXrLink(_LinkDict):
    """COL XR record linked to the GBIF link (`LinkEntry.col_xr`)."""

    name: str
    author: str | None
    rank: str | None
    extinct: bool | None


class WikipediaPortals(_LinkDict):
    """Portals of the retained parent article."""

    portals: list[str]
    rank: str
    name: str


class PageRef(_LinkDict):
    """Page of a Wikipedia sister project (`LinkEntry.commons`…)."""

    page: str


class WikidataRef(_LinkDict):
    """Reference to a Wikidata item."""

    id: str


class LinkEntry(_LinkDict, total=False):
    """Entry of `Struct.links[<module-id>]`.

    Every key is optional: each module writes only its own. A
    TypedDict, not `dict[str, Any]`, so a misspelled key is a type
    error. Shared keys: `id`, `name`, `rank`, `author`, `extinct`,
    `synonym`, `detected_status`; the others belong to one module or to
    the `wikimedia` and `footer` pseudo-modules.
    """

    id: str | int | None
    name: str
    rank: str | None
    author: str | None
    extinct: bool | None
    synonym: bool | None
    invalid: bool
    # "synonyme" or "accepté", as reported by the module; see
    # `RankInconsistency`.
    detected_status: str
    detected_kingdom: str
    detected_family: str
    detected_order: str
    synonym_name: str
    synonym_id: str | int | None
    url: str | None
    link: str | None
    key: int
    inpn_id: str | int
    col_xr: ColXrLink
    probable_year: int
    common_name: str
    ids: list[Any]
    genus: str | None
    epithet: str | None
    species: str
    family: str | None
    date: str
    citation: str
    risk: str
    criterion: str
    appendix: str
    precision: str
    wikidata: WikidataRef
    commons: PageRef
    commons_category: PageRef
    wikispecies: PageRef
    frwiktionary: PageRef
    wikipedia: WikipediaPortals
    existing_categories: dict[str, bool]
    portals: list[str]
    categories: list[str]


class TaxonInfo(_Model):
    """Name, rank and author of the requested taxon, as resolved."""

    name: str
    rank: str | None = None
    author: str | None = None
    extinct: bool | None = None
    # Wikified author text (known authors and years linked, {{auteur}}
    # for the rest), computed once during orchestration by
    # `resolve_main_author`, which needs `kingdom`. None until then;
    # rendering reads it instead of the raw `author`.
    resolved_author: str | None = None


class RankName(_Model):
    """Taxon entry in a parent, sub-taxon or synonym list."""

    name: str
    rank: str | None = None
    author: str | None = None
    extinct: bool | None = None


class Basionym(_Model):
    """Basionym; `source` is the module that supplied it."""

    name: str
    author: str | None = None
    source: str


class TypeTaxon(_Model):
    """Type taxon, the lower-rank taxon that created this one."""

    name: str
    rank: str | None = None
    author: str | None = None
    source: str


class SubTaxonList(_Model):
    """Lower-rank taxa."""

    items: list[RankName] = Field(default_factory=list)
    source: str | None = None
    # True if the list was cut by the `limite-listes` option.
    truncated: bool = False


class SynonymList(_Model):
    """Synonyms of the taxon."""

    items: list[RankName] = Field(default_factory=list)
    source: str | None = None
    truncated: bool = False


class Etymology(_Model):
    """Etymology text and its source module."""

    text: str
    source: str


class DistributionEntry(_Model):
    """Country codes of one module's distribution.

    Each dict maps a code to itself, so membership is a key lookup.
    `introduced` and `extinct` are subsets of the other two.
    """

    certain: dict[str, str] = Field(default_factory=dict)
    uncertain: dict[str, str] = Field(default_factory=dict)
    introduced: dict[str, str] = Field(default_factory=dict)
    extinct: dict[str, str] = Field(default_factory=dict)


class KingdomInconsistency(_Model):
    """Enrichment module whose kingdom differs from the retained one.

    Possible cross-kingdom homonym. Only detected when the module
    exposes the kingdom without an extra network call.
    """

    module: str
    suggested_kingdom: str
    retained_kingdom: str


class RankInconsistency(_Model):
    """Competing classification module disagreeing on a value.

    Both sources have a value for the family, order or status, and
    the values differ. Never resolved automatically.
    """

    module: str
    # Compared field: "famille", "ordre" or "statut".
    compared_field: str
    suggested_value: str
    retained_value: str


class Struct(_Model):
    """Mutable state passed through the whole pipeline.

    Classification resolution, module enrichment, then rendering.
    `links[<module-id>]` is typed by `LinkEntry`.
    """

    taxon: TaxonInfo
    classification: str = ""
    classification_taxobox: str = ""
    domain: str = "*"
    kingdom: str = ""
    # Higher taxa, nearest first; the order matters for the taxobox.
    ranks: list[RankName] = Field(default_factory=list)

    links: dict[str, LinkEntry] = Field(default_factory=dict)

    basionym: Basionym | None = None
    subtaxa: SubTaxonList | None = None
    # module -> language code -> names (see `langues.code_langue`).
    # Only "fr" is rendered; see `vernacular_names`.
    vernacular: dict[str, dict[str, list[str]]] = Field(default_factory=dict)

    # module -> status -> names, for names a source labels itself (e.g.
    # TelaMétro's "Recommandé ou typique"), rendered apart; see
    # `sections.render_systematics`.
    other_names: dict[str, dict[str, list[str]]] = Field(default_factory=dict)

    # source -> sentences of the "Description" section, rendered with
    # one {{Bioref}} per source; see `sections.render_description`.
    description: dict[str, list[str]] = Field(default_factory=dict)

    etymology: Etymology | None = None
    original_publication: str | list[str] | None = None
    synonyms: SynonymList | None = None
    type_taxon: TypeTaxon | None = None
    distribution: dict[str, DistributionEntry] = Field(default_factory=dict)

    # Lets a module hide the taxobox kingdom field instead of showing
    # an inconsistent value (e.g. when a synonym changes kingdom).
    hide_kingdom: bool = False

    # Taxobox 'image' and 'legende' keys, when a source provides them.
    image: dict[str, str] | None = None

    # 'marin' or 'terrestre' when a source says so, else None. Used by
    # the portal selector; see `selectors.rules.portails`.
    habitat: str | None = None

    def vernacular_names(self, language: str) -> dict[str, list[str]]:
        """Return `vernacular` restricted to `language`."""
        return {
            module: languages[language]
            for module, languages in self.vernacular.items()
            if languages.get(language)
        }
