"""VASCAN module (database of vascular plants of Canada).

Botanical enrichment only (author, French vernacular names, id), domain
`végétal`. Deliberately regional (the flora of Canada), not a general
classification. `higherClassification` (a `;`-separated chain of
ancestor names) is not used for `struct.ranks`: the API gives no rank
per element (subfamily and section mix there), so rebuilding the rank by
position would be fragile. Like CITES, NCBI and TelaMétro, it reuses the
known `struct.taxon.rank`.

VASCAN distinguishes synonyms from accepted names (`taxonomicStatus`);
this module does not follow the accepted target (it does not affect
classification), it only marks the status, like the other enrichment
modules.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.langues import groupe_par_langue
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.core.selectors.coherence import reference_module_is_consistent
from organon.modules.common import format_author, simple_debug_link
from organon.modules.vascan.adapter import VascanAdapter


class VascanModule(TaxonomyModule):
    """VASCAN module."""

    meta = ModuleMeta(
        id="vascan", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: VascanAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or VascanAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from VASCAN."""
        # The domain filter is bypassed when the domain is unknown ("*")
        if not reference_module_is_consistent(self.meta.id, struct.kingdom):
            return None
        # `search` is fuzzy (e.g. "Chaetodon" returns
        # "Astragalus chaetodon"): only an exact scientific name is the
        # same taxon.
        wanted = struct.taxon.name.casefold()
        match = next(
            (
                m
                for m in await self._adapter.search(struct.taxon.name)
                if m["canonicalName"].casefold() == wanted
            ),
            None,
        )
        if match is None:
            return None

        vascan_link: LinkEntry = {
            "id": match["taxonID"],
            "name": match["canonicalName"],
            "author": format_author(match.get("scientificNameAuthorship")),
        }
        assertions = match.get("taxonomicAssertions") or []
        if assertions and assertions[0].get("taxonomicStatus") != "accepted":
            vascan_link["synonym"] = True
        struct.links["vascan"] = vascan_link

        vernacular = groupe_par_langue(
            (e.get("language"), e.get("vernacularName"))
            for e in match.get("vernacularNames") or []
        )
        if vernacular:
            struct.vernacular["VASCAN"] = vernacular

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{VASCAN}} template."""
        data = struct.links.get("vascan")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            target += " " + author
        synonym_flag = " | nv" if data.get("synonym") else ""
        return f"{{{{VASCAN | {data['id']} | {target}{synonym_flag} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the VASCAN page."""
        return simple_debug_link(
            struct, "vascan", "https://data.canadensys.net/vascan/taxon/{id}", "VASCAN"
        )


register_module(VascanModule)
