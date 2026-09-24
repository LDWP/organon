"""WFO module: classification (domain `végétal`), id and author.

Limited to `accepted` names (see adapter.py). Each ancestor carries its
exact rank, including "Angiosperms" (`wfo-9949999999`), accepted at
phylum rank though without a Latin ending or author.

`taxonNameSuggestion` may return several records with the same name
(homonyms, e.g. "Quercus robur"): WFO gives each an explicit role
(`accepted`, `synonym`, `unplaced`), used as the preference signal, like
IPNI's `inPowo`. No synonym following: a non-`accepted` record serves
enrichment but yields no classification, rather than rerun the
collection on a possibly absent accepted name.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author, simple_debug_link
from organon.modules.wfo.adapter import WfoAdapter
from organon.modules.wfo.ranks import wfo_to_wp_rank


class WfoModule(TaxonomyModule):
    """WFO module."""

    meta = ModuleMeta(
        id="wfo", can_classify=True, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: WfoAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or WfoAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from WFO."""
        taxon = struct.taxon.name
        results = await self._adapter.search(taxon)
        exact = [r for r in results if r["nom"] == taxon]
        if not exact:
            return None
        match = next((r for r in exact if r["statut"] == "accepted"), exact[0])

        struct.links["wfo"] = {
            "id": match["id"],
            "name": match["nom"],
            "author": format_author(match.get("auteur")),
        }

        if not is_classification:
            return struct
        if match["statut"] != "accepted":
            return None

        ancestors = await self._adapter.ancestors(match["id"])
        ranks = [
            RankName(name=a["nom"], author=format_author(a["auteur"]), rank=rank)
            for a in ancestors
            if (rank := wfo_to_wp_rank(a["rang_brut"])) is not None and rank != "règne"
        ]

        struct.taxon.rank = wfo_to_wp_rank(match.get("rang_brut"))
        struct.taxon.author = format_author(match.get("auteur"))
        struct.kingdom = "végétal"
        struct.classification = "WFO"
        struct.classification_taxobox = "WFO"
        struct.ranks = ranks
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{WFO}} template.

        The template italicizes parameter 2 and rebuilds the `wfo-`
        prefix itself, so parameter 1 is the id WITHOUT it.
        """
        data = struct.links.get("wfo")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        author = f" | {data['author']}" if data.get("author") else ""
        wfo_id = str(data["id"]).removeprefix("wfo-")
        return f"{{{{WFO | {wfo_id} | {data['name']}{author} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the WFO page."""
        return simple_debug_link(
            struct, "wfo", "https://www.worldfloraonline.org/taxon/{id}", "WFO"
        )


register_module(WfoModule)
