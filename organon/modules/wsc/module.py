"""World Spider Catalog (WSC) module: classification of spiders.

From the daily CSV export (see adapter.py); no REST API, which needs a
WSCA registration and a personal key, unusable by an automated service
without a dedicated account.

The CSV only covers family, genus, species and subspecies. The whole
catalog being Araneae (class Arachnida, phylum Arthropoda), that fixed
chain is injected directly, as
`organon.modules.powo.ranks.POWO_KINGDOM_MAP` does.

No synonym resolution: the export covers "all currently valid species",
so a synonym never appears. Only the REST API exposes that link, so a
search on a synonym simply fails (`search` returns None).

`can_render_external_link=False` (no {{Bioref}}): the export license is
non-commercial, so the source is exposed only as internal
classification, not as a public citation link.

No geographic distribution: the CSV `distribution` field is free text of
English country names with no structured code, and the repository has no
country-name to code table; an improvised one would produce invented
codes.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.common import format_author, simple_debug_link
from organon.modules.wsc.adapter import WscAdapter

# WSC covers a single phylum, class and order (the whole catalog is
# Araneae), absent from the CSV (family, genus, species only): injected
# rather than queried.
_FIXED_CHAIN = (
    RankName(name="Araneae", rank="ordre"),
    RankName(name="Arachnida", rank="classe"),
    RankName(name="Arthropoda", rank="embranchement"),
)


def _format_author_wsc(row: dict) -> str | None:
    """Return the author and year of a row, parenthesized if needed."""
    author, year = row.get("author"), row.get("year")
    if not author:
        return None
    raw = f"{author}, {year}" if year else author
    if row.get("parentheses") == "1":
        raw = f"({raw})"
    return format_author(raw)


class WscModule(TaxonomyModule):
    """WSC module."""

    meta = ModuleMeta(
        id="wsc",
        can_classify=True,
        can_render_external_link=False,
        domains=["arachnide"],
        priority=990,
    )

    def __init__(self, adapter: WscAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or WscAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from the WSC export."""
        row = await self._adapter.search(struct.taxon.name)
        if row is None:
            return None

        struct.links["wsc"] = {"id": row["speciesId"], "name": struct.taxon.name}

        if not is_classification:
            return struct

        subspecies = bool(row.get("subspecies")) and struct.taxon.name == (
            f"{row['genus']} {row['species']} {row['subspecies']}"
        )
        struct.taxon.rank = "sous-espèce" if subspecies else "espèce"
        struct.taxon.author = _format_author_wsc(row)
        struct.kingdom = "animal"
        struct.classification = "WSC"
        struct.classification_taxobox = "WSC"

        ranks: list[RankName] = []
        if subspecies:
            ranks.append(RankName(name=f"{row['genus']} {row['species']}", rank="espèce"))
        ranks.extend(
            (
                RankName(name=row["genus"], rank="genre"),
                RankName(name=row["family"], rank="famille"),
            )
        )
        ranks.extend(_FIXED_CHAIN)
        struct.ranks = ranks

        return struct

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the WSC page."""
        return simple_debug_link(struct, "wsc", "https://wsc.nmbe.ch/species/{id}", "WSC")


register_module(WscModule)
