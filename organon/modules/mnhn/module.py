"""MNHN module (science.mnhn.fr): enrichment only.

`can_classify=False`, limited to species and genus ranks: the site has a
dedicated page for those two levels only.

Fixed bug (verified): the URL used to be built by replacing the space
with `/_` (e.g. `species/gadus/_morhua`), which always returns 404; the
right separator is a plain `/` (`species/gadus/morhua`). Without the fix
the module could never find any species.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.mnhn.adapter import MnhnAdapter

_RANK_PATH = {"espèce": "species", "genre": "genus"}


class MnhnModule(TaxonomyModule):
    """MNHN module."""

    meta = ModuleMeta(id="mnhn", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: MnhnAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or MnhnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the MNHN page of the taxon."""
        if is_classification:
            return None

        rank = struct.taxon.rank
        segment = _RANK_PATH.get(rank or "")
        if segment is None:
            return None

        slug = struct.taxon.name.lower().replace(" ", "/")
        path = f"{segment}/{slug}"

        if not await self._adapter.exists(path):
            return None

        struct.links["mnhn"] = {
            "id": slug,
            "rank": rank,
            "url": f"https://science.mnhn.fr/taxon/{path}",
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{MNHN}} template."""
        data = struct.links.get("mnhn")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        description = wp_apply_italics(
            struct.taxon.name, data.get("rank") or struct.taxon.rank, struct.kingdom
        )
        return (
            f"{{{{MNHN | {data['rank']} | {data['id']} | {description} | consulté le={cdate}}}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the MNHN page."""
        data = struct.links.get("mnhn")
        if not data or "url" not in data:
            return None
        return f"<a href='{data['url']}' target='_blank' rel='noopener noreferrer'>MNHN</a>"


register_module(MnhnModule)
