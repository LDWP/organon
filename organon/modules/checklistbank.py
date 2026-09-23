"""Generic adapter and module base for ChecklistBank datasets."""

from __future__ import annotations

from functools import partial
from typing import ClassVar, Literal
from urllib.parse import quote

from organon.core.config import GenerateOptions
from organon.core.http import MinIntervalThrottle, OwnedClientMixin, fetch_json
from organon.core.models import LinkEntry, RankName, Struct, SubTaxonList, SynonymList
from organon.core.registry import TaxonomyModule
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.bibliography import resolve_doi_citation
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.common import (
    as_limit,
    checklistbank_accepted_name,
    checklistbank_children_page,
    checklistbank_synonyms,
    collect_pages,
    follow_synonym,
    format_author,
)

API_BASE = "https://api.checklistbank.org"

# One budget for every dataset: they share the same API host.
_throttle = MinIntervalThrottle(0.2).wait


class ChecklistBankAdapter(OwnedClientMixin):
    """Raw HTTP access to one ChecklistBank dataset."""

    def __init__(self, dataset_id: str, *args, **kwargs) -> None:
        """Bind the adapter to one dataset."""
        super().__init__(*args, throttle=_throttle, **kwargs)
        self.dataset_id = dataset_id

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation (see bibliography)."""
        return await resolve_doi_citation(self._client, doi)

    async def search(self, taxon: str) -> list[dict]:
        """Return the exact-name usages found in the dataset."""
        data = await fetch_json(
            self._client,
            f"{API_BASE}/dataset/{self.dataset_id}/nameusage/search",
            params={
                "limit": 50,
                "offset": 0,
                "q": taxon,
                "sortBy": "taxonomic",
                "status": "_NOT_NULL",
                "type": "EXACT",
            },
            empty_value={},
        )
        return data.get("result", [])

    async def children_page(self, taxon_id: str, offset: int = 0) -> dict:
        """Return a page of children of a taxon."""
        return await checklistbank_children_page(
            self._client, API_BASE, self.dataset_id, taxon_id, offset
        )

    async def taxon(self, taxon_id: str) -> dict:
        """Return one taxon record, or an empty dict if absent."""
        return await fetch_json(
            self._client,
            f"{API_BASE}/dataset/{self.dataset_id}/taxon/{quote(taxon_id, safe='')}",
            empty_value={},
        )

    async def synonyms(self, taxon_id: str) -> dict:
        """Return the synonyms of a taxon."""
        return await checklistbank_synonyms(self._client, API_BASE, self.dataset_id, taxon_id)


class ChecklistBankModule(TaxonomyModule):
    """Classification module backed by a single ChecklistBank dataset.

    Subclasses declare `meta`, `dataset_id`, `label` and `site_name`,
    and may override the other class attributes or the `_extra_links`
    and rendering hooks.

    Everything must be verifiable on Wikipedia: a module that cannot
    cite a page of the source's own site neither classifies nor
    supplies content, so it must not exist. `_page_url` never falls
    back to checklistbank.org; a subclass must set `link_source` or
    override `_page_url` or `render_bioref` (enforced at class
    creation). A taxon whose record has no link renders no bioref, and
    a synonym without a link of its own borrows the accepted taxon's.
    """

    dataset_id: ClassVar[str]
    label: ClassVar[str]
    site_name: ClassVar[str]
    kingdom: ClassVar[str] = "animal"
    # Ranks above the dataset's root, absent from the API's
    # `classification`.
    fixed_chain: ClassVar[tuple[RankName, ...]] = ()
    # Where the API exposes an external page URL, if anywhere.
    link_source: ClassVar[Literal["usage", "name"] | None] = None
    has_synonyms: ClassVar[bool] = True
    debug_label: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs) -> None:
        """Reject a dataset that cannot cite its own site."""
        super().__init_subclass__(**kwargs)
        base = ChecklistBankModule
        cites = (
            cls.link_source is not None
            or cls._page_url is not base._page_url
            or cls.render_bioref is not base.render_bioref
        )
        if not (cites and cls.meta.can_render_external_link):
            raise TypeError(f"{cls.__name__} cannot cite a page of its source's own site")

    def __init__(self, adapter: ChecklistBankAdapter | None = None) -> None:
        """Use `adapter` if given, else create one for the dataset."""
        self._adapter = adapter or ChecklistBankAdapter(self.dataset_id)

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from the dataset."""
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        """Collect with a synonym hop count."""
        candidates = await self._adapter.search(struct.taxon.name)
        if not candidates:
            return None

        accepted = [r for r in candidates if r["usage"]["status"] == "accepted"]
        if accepted:
            current = accepted[0]
        elif options.follow_synonyms:
            current = candidates[0]
        else:
            return None

        usage = current["usage"]
        name = usage["name"]
        taxon_id = current["id"]
        rank = col_xr_to_wp_rank(name["rank"])

        link: LinkEntry = {
            "id": taxon_id,
            "name": name["scientificName"],
            "author": format_author(name.get("authorship")),
            "rank": rank,
            **self._extra_links(current),
            **({"extinct": usage["extinct"]} if "extinct" in usage else {}),
        }
        struct.links[self.meta.id] = link
        if (
            usage["status"] == "synonym"
            and self.link_source
            and not link.get("link")
            # The accepted hop overwrites it.
            and not (is_classification and options.follow_synonyms)
        ):
            link["link"] = await self._accepted_link(usage)

        is_synonym = usage["status"] == "synonym"
        link["detected_status"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            handled, result = await follow_synonym(
                struct,
                self.meta.id,
                is_classification,
                options,
                hop,
                partial(checklistbank_accepted_name, usage),
                lambda next_hop: self._collect(struct, is_classification, options, hop=next_hop),
            )
            if handled:
                return result

        if not is_classification:
            return struct

        struct.taxon.author = format_author(name.get("authorship"))
        struct.taxon.rank = rank
        if "extinct" in usage:
            struct.taxon.extinct = usage["extinct"]
        struct.taxon.name = name["scientificName"].strip()
        struct.classification = self.label
        struct.classification_taxobox = self.label
        struct.kingdom = self.kingdom
        struct.ranks = [
            RankName(
                name=c["name"],
                rank=col_xr_to_wp_rank(c["rank"]),
                author=format_author(c.get("authorship")),
            )
            for c in reversed(current.get("classification", []))
            if c.get("id") != taxon_id
        ] + list(self.fixed_chain)

        children, truncated = await collect_pages(
            lambda offset: self._children(taxon_id, offset),
            limit=as_limit(options.list_limit),
        )
        if children:
            struct.subtaxa = SubTaxonList(items=children, source=self.label, truncated=truncated)

        if self.has_synonyms:
            synonyms = await self._synonyms(taxon_id)
            if synonyms:
                struct.synonyms = SynonymList(items=synonyms, source=self.label, truncated=False)

        return struct

    async def _children(self, taxon_id: str, offset: int) -> tuple[list[RankName], int, bool]:
        """Return (sub-taxa, raw count, last page?) for one page."""
        page = await self._adapter.children_page(taxon_id, offset)
        raw = page.get("result", [])
        children = [
            RankName(
                name=c["name"],
                rank=col_xr_to_wp_rank(c["rank"]),
                author=format_author(c.get("authorship")),
                extinct=c.get("labelHtml", "").startswith("†") or None,
            )
            for c in raw
            if c.get("rank") != "unranked" and c.get("status") == "accepted"
        ]
        return children, len(raw), page.get("last", True)

    async def _synonyms(self, taxon_id: str) -> list[RankName]:
        """Return the synonyms of a taxon."""
        data = await self._adapter.synonyms(taxon_id)
        synonyms = []
        for entry in [*data.get("homotypic", []), *data.get("heterotypic", [])]:
            name = entry.get("name") or {}
            if not name.get("scientificName"):
                continue
            synonyms.append(
                RankName(
                    name=name["scientificName"],
                    author=format_author(name.get("authorship")),
                    rank=col_xr_to_wp_rank(name.get("rank", "")),
                )
            )
        return synonyms

    def _extra_links(self, current: dict) -> LinkEntry:
        """Return the dataset-specific link fields."""
        if self.link_source is None:
            return {}
        return {"link": self._usage_link(current["usage"])}

    def _usage_link(self, usage: dict) -> str | None:
        """Return the source-site URL carried by a usage, if any."""
        return usage.get("link") if self.link_source == "usage" else usage["name"].get("link")

    async def _accepted_link(self, usage: dict) -> str | None:
        """Return the accepted taxon's source-site URL."""
        accepted_id = (usage.get("accepted") or {}).get("id")
        if accepted_id is None:
            return None
        return self._usage_link(await self._adapter.taxon(accepted_id) or {"name": {}})

    def _page_url(self, data: LinkEntry) -> str | None:
        """Return the URL of the taxon page on the source's site."""
        return data.get("link")

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{Lien web}} citation."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data or not (url := self._page_url(data)):
            return None
        target = wp_apply_italics(
            data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        if author := data.get("author"):
            target += " " + author
        suffix = " <small>(non valide)</small>" if data.get("synonym") else ""
        return (
            f"{{{{Lien web | langue=en | titre={target} | url={url} "
            f"| site={self.site_name} | consulté le={retrieval_dates()} }}}}{suffix}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the taxon page."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data:
            return None
        label = self.debug_label or self.label
        # Debug aid only, never cited: ChecklistBank page fallback.
        url = self._page_url(data) or (
            f"https://www.checklistbank.org/dataset/{self.dataset_id}/taxon/{data['id']}"
        )
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{label}</a>"
