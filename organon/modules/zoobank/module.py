"""ZooBank module: the official registry of zoological nomenclature.

Served through ChecklistBank dataset 2037. Domain `animal`.

Unlike `organon.modules.col` and `bryonames`, ZooBank is NOT a
classification source (`can_classify=False`, like
`organon.modules.ipni`): it is a registry of nomenclatural acts (who
published which name, where, when), not a taxonomic reference. Its
`classification` chain and accepted/synonym status do not reflect a
reliable current taxonomic opinion (e.g. "Bufo vulgaris" Laurenti, 1768
is "accepted" there). So no synonym following and no `ranks`, `subtaxa`
or `synonyms` fields: only an enrichment (author, rank, original
publication citation). An unreliable source must not inject a
classification opinion.

Original publication: `usage.accordingTo` gives a formatted citation of
the original nomenclatural act, with no extra call. Written
unconditionally like IPNI (same priority limitation on concurrent
writes, see `organon.modules.ipni.module`).

Citation link: `name.link` (`http://zoobank.org/<uuid>`) redirects to
the `/NomenclaturalActs/<uuid>` page of zoobank.org with the full
record. A bare HTTP client may seem to hit a dead link (a 404 after the
redirect): that is zoobank.org's anti-robot banner for a client without
JavaScript. Without
`link`, no debug link (no ChecklistBank fallback).

`render_bioref` uses the dedicated `{{ZooBank}}` template, which
italicizes its parameter 2 itself, like `{{IPNI}}`: the name is passed
raw, not through `wp_apply_italics`.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.bibliography import citation_or_text
from organon.modules.checklistbank import ChecklistBankAdapter
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.common import format_author

DATASET_ID = "2037"  # alias "ZooBank DwCA", DOI 10.48580/d4g9


class ZoobankModule(TaxonomyModule):
    """ZooBank module."""

    meta = ModuleMeta(
        id="zoobank", can_classify=False, can_render_external_link=True, domains=["animal"]
    )

    def __init__(self, adapter: ChecklistBankAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or ChecklistBankAdapter(DATASET_ID)

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the nomenclatural record of the taxon."""
        candidates = await self._adapter.search(struct.taxon.name)
        exact = [
            r for r in candidates if r["usage"]["name"]["scientificName"] == struct.taxon.name
        ]
        if not exact:
            return None

        cur = next((r for r in exact if r["usage"]["status"] == "accepted"), exact[0])
        usage = cur["usage"]
        name = usage["name"]

        struct.links["zoobank"] = {
            "id": cur["id"],
            "name": name["scientificName"],
            "author": format_author(name.get("authorship")),
            "rank": col_xr_to_wp_rank(name["rank"]),
            "link": name.get("link"),
        }

        struct.original_publication = await citation_or_text(
            self._adapter.resolve_doi_citation, usage.get("accordingTo")
        )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{ZooBank}} template.

        The name is NOT italicized here: the template does it for
        parameter 2 (same as `{{IPNI}}`).
        """
        data = struct.links.get("zoobank")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        author = f" | {data['author']}" if data.get("author") else ""
        return f"{{{{ZooBank | {data['id']} | {data['name']}{author} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the ZooBank record."""
        data = struct.links.get("zoobank")
        if not data or "id" not in data or not (url := data.get("link")):
            return None
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>ZooBank</a>"


register_module(ZoobankModule)
