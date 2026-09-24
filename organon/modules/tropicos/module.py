"""Tropicos module: botanical enrichment (author, id).

Domain `végétal`. No classification: like CITES, NCBI, TelaMétro, IPNI
and VASCAN, it reuses the known `struct.taxon.rank`.

`Search/NameLookup` may return several records with exactly the same
`fullName` (e.g. *Quercus robur*: "(Ten.) A. DC." and "L.").
`correctNameId` stays `null` there, but `displayName` prefixes the name
Tropicos retains with `!` (`!!` for a conserved name) and the synonyms
with `*` or `**`. `nameKindId` is unused: it is 2 as well as 4 for
accepted names. So exact `fullName` results are filtered, the one
prefixed `!` preferred, else the first (a known limit, e.g. Arabidopsis
thaliana has no `!` but a single exact match).

`authorString` is used directly (ready-made field).
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.tropicos.adapter import TropicosAdapter


class TropicosModule(TaxonomyModule):
    """Tropicos module."""

    meta = ModuleMeta(
        id="tropicos", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: TropicosAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or TropicosAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from Tropicos."""
        results = await self._adapter.search(struct.taxon.name)
        exact = [r for r in results if r.get("fullName") == struct.taxon.name]
        if not exact:
            return None
        match = next((r for r in exact if r.get("displayName", "").startswith("!")), exact[0])

        struct.links["tropicos"] = {
            "id": match["id"],
            "name": match["fullName"],
            "author": format_author(match.get("authorString")),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{Tropicos}} template.

        The template italicizes parameter 2 itself, unconditionally (as
        {{IPNI}}), so the name is passed as is. The author goes in
        parameter 3, outside the italics.
        """
        data = struct.links.get("tropicos")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        author = f" | {data['author']}" if data.get("author") else ""
        return f"{{{{Tropicos | {data['id']} | {data['name']}{author} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the Tropicos page."""
        return simple_debug_link(struct, "tropicos", "https://tropicos.org/name/{id}", "Tropicos")


register_module(TropicosModule)
