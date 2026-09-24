"""IPNI module (International Plant Names Index): botanical enrichment.

Author and id only, domain `végétal`. No classification: IPNI is an
index of published names, not a hierarchical taxonomy. Like CITES, NCBI
and TelaMétro, it reuses the known `struct.taxon.rank` rather than
translating its own abbreviated markers.

`search()` mixes name, publication and author records; only a name
record has a `name` field, which is enough to filter.

IPNI indexes EVERY publication of a name combination, including late
homonyms: "Quercus robur" has three records (Linnaeus 1753, Asso 1779,
Pallas 1789). `inPowo` (true only on the 1753 record) is a reliable
signal to prefer the combination Plants of the World Online currently
recognizes, rather than the first answer in an unguaranteed order.

Original publication: see `citations.build_citation`. Written
unconditionally (IPNI never classifies). As any single-value field
(`_MONOVALUE_FIELDS`), the value kept on a concurrent write by another
enrichment module depends on `ModuleMeta.priority` (IPNI keeps the
default 0), a limitation that predates this feature.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, format_author_year, simple_debug_link
from organon.modules.ipni import citations
from organon.modules.ipni.adapter import IpniAdapter


class IpniModule(TaxonomyModule):
    """IPNI module."""

    meta = ModuleMeta(
        id="ipni", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: IpniAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or IpniAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from IPNI."""
        results = await self._adapter.search(struct.taxon.name)
        exact = [r for r in results if r.get("name") == struct.taxon.name]
        match = next((r for r in exact if r.get("inPowo")), exact[0] if exact else None)
        if match is None:
            return None

        url = match.get("url") or ""
        ipni_id = url.removeprefix("/n/")
        if not ipni_id:
            return None

        raw_author = match.get("authors") or match.get("publishingAuthor")
        struct.links["ipni"] = {
            "id": ipni_id,
            "name": match["name"],
            "author": format_author(format_author_year(raw_author, match.get("publicationYear"))),
        }
        struct.original_publication = await citations.build_citation(self._adapter, match)
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{IPNI}} template.

        The template italicizes parameter 2 itself, unconditionally, so
        the name is passed as is, not through `wp_apply_italics`. The
        author goes in parameter 3, after the name and outside the
        italics.
        """
        data = struct.links.get("ipni")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        author = f" | {data['author']}" if data.get("author") else ""
        return f"{{{{IPNI | {data['id']} | {data['name']}{author} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the IPNI page."""
        return simple_debug_link(struct, "ipni", "https://www.ipni.org/n/{id}", "IPNI")


register_module(IpniModule)
