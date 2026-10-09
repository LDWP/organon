"""FishBase, via its WoRMS-derived ChecklistBank export (1010)."""

import logging

import httpx

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.checklistbank import ChecklistBankAdapter, ChecklistBankModule
from organon.modules.fishbase.adapter import FishbaseSiteAdapter

logger = logging.getLogger(__name__)


class FishbaseModule(ChecklistBankModule):
    """FishBase module, with templates for species to orders."""

    meta = ModuleMeta(
        id="fishbase", can_classify=True, can_render_external_link=True, domains=["poisson"]
    )
    dataset_id = "1010"  # alias "WoRMS FishBase", resynced 2026-09-02
    label = "FishBase"
    site_name = "FishBase"

    def __init__(
        self,
        adapter: ChecklistBankAdapter | None = None,
        site: FishbaseSiteAdapter | None = None,
    ) -> None:
        """Use `adapter` and `site` if given, else create them."""
        super().__init__(adapter)
        self._site = site or FishbaseSiteAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect from ChecklistBank, then add the FishBase code."""
        result = await super().collect(struct, is_classification, options)
        data = result.links.get(self.meta.id) if result else None
        if data and data.get("detected_status") == "accepté":
            await self._add_code(data)
        return result

    async def _add_code(self, data: LinkEntry) -> None:
        """Set `code` for species and families, if the site knows it."""
        rank = data.get("rank")
        if rank == "espèce":
            lookup = self._site.species_code
        elif rank == "famille":
            lookup = self._site.family_code
        else:
            return
        try:
            code = await lookup(data["name"])
        except httpx.HTTPError as exc:
            logger.warning("fishbase: code lookup failed for %s: %s", data["name"], exc)
            return
        if code:
            data["code"] = code

    def render_bioref(self, struct: Struct) -> str | None:
        """Render a FishBase template, or None if not citable."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data:
            return None
        rank = data.get("rank") or struct.taxon.rank
        date = retrieval_dates()
        suffix = " <small>(non valide)</small>" if data.get("synonym") else ""
        if rank == "genre":
            return f"{{{{FishBase genre | {data['name']} | consulté le={date} }}}}{suffix}"
        if rank == "ordre":
            author = f" | {data['author']}" if data.get("author") else ""
            return f"{{{{FishBase ordre | {data['name']}{author} | consulté le={date} }}}}{suffix}"
        if data.get("code") and rank in ("espèce", "famille"):
            label = wp_apply_italics(data["name"], rank, struct.kingdom)
            if rank == "espèce" and data.get("author"):
                label += f" {data['author']}"
            code = data["code"]
            return f"{{{{FishBase {rank} | {code} | {label} | consulté le={date} }}}}{suffix}"
        # No numeric code, no FishBase page to cite: the export's WoRMS
        # pages are not FishBase sources.
        return None


register_module(FishbaseModule)
