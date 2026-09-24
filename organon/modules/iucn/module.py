"""IUCN Red List module: conservation status.

Enrichment only (no classification). It feeds `{{Taxobox UICN}}` (see
`sections.render_taxobox`) and the reference template `{{UICN}}` (see
`render_bioref`), which the template documentation pairs. `{{UICN}}`
expects the numeric taxon code on iucnredlist.org as first parameter:
the `sis_id` already in the `/taxa/scientific_name` answer (no extra
call), matching Wikidata property P627.

It replaces the former GBIF passenger, which exposed only the category
code, not the assessment criteria (e.g. "A2abd+4abd"). The
`struct.links` key is now `"iucn"`, aligned with `meta.id`: the old
`"uicn"` key silently kept `compute_ext_link_items` from finding this
module by id, making `render_bioref` unreachable.

A taxon often has several assessments, one per geographic scope (Global,
Europe…), each possibly "latest" in its own scope: see
`_selected_global_assessment`. Only the most recent Global (code "1")
one is the reference status, the only relevant for a general infobox.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author
from organon.modules.iucn.adapter import IucnAdapter

_RANK_MARKERS = {"subsp.", "ssp.", "var.", "f.", "forma"}
_GLOBAL_SCOPE = "1"


def _split_scientific_name(name: str) -> tuple[str, str, str | None] | None:
    """Split a name into genus, species and infraspecific epithets.

    As `genus_name`, `species_name` and `infra_name` expect; an explicit
    rank marker (e.g. "subsp.") is ignored. None under two words: IUCN
    never assesses a supraspecific rank.
    """
    words = [m for m in name.split() if m not in _RANK_MARKERS]
    if len(words) < 2:
        return None
    genus, species, *rest = words
    return genus, species, (rest[-1] if rest else None)


def _selected_global_assessment(assessments: list[dict]) -> dict | None:
    """Return the latest assessment of global scope, or None."""
    return next(
        (
            a
            for a in assessments
            if a.get("latest")
            and any(s.get("code") == _GLOBAL_SCOPE for s in a.get("scopes") or [])
        ),
        None,
    )


class IucnModule(TaxonomyModule):
    """IUCN Red List module."""

    meta = ModuleMeta(
        id="iucn",
        can_classify=False,
        can_render_external_link=True,
        domains="all",
        # Highest priority of the repository (above COL, 999):
        # `EnrichmentRunner.run` merges `struct.links` module by module
        # in increasing priority, the last applied winning on a shared
        # key. Nobody else writes `links["iucn"]` today, but GBIF used
        # to write `links["uicn"]`: if that write came back by mistake,
        # this priority makes the direct IUCN data (with criteria) win
        # over a poorer passenger.
        priority=1000,
    )

    def __init__(self, adapter: IucnAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or IucnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the conservation status of the taxon."""
        if is_classification:
            return None  # IUCN never provides a classification

        parsed = _split_scientific_name(struct.taxon.name)
        if parsed is None:
            return None
        genus, species, infra = parsed

        data = await self._adapter.scientific_name(genus, species, infra)
        if not data:
            return None

        evaluation = _selected_global_assessment(data.get("assessments") or [])
        if evaluation is None or not evaluation.get("red_list_category_code"):
            return None

        taxon = data.get("taxon") or {}
        struct.links["iucn"] = {
            "id": taxon.get("sis_id"),
            "name": taxon.get("scientific_name") or struct.taxon.name,
            "author": format_author(taxon.get("authority")),
            "risk": evaluation["red_list_category_code"],
            "criterion": evaluation.get("criteria") or "",
            "url": evaluation.get("url"),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{UICN}} template."""
        data = struct.links.get("iucn")
        if not data or not data.get("id"):
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            target += " " + author
        return f"{{{{UICN | {data['id']} | {target} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the IUCN page."""
        data = struct.links.get("iucn")
        if not data or not data.get("url"):
            return None
        return f"<a href='{data['url']}' target='_blank' rel='noopener noreferrer'>UICN</a>"


register_module(IucnModule)
