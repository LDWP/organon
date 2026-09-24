"""INPN/TAXREF module: classification and French vernacular names.

The lineage is rebuilt from the detail page breadcrumb, each ancestor
resolved individually to get its rank (see adapter.py).

No synonym following: a taxon whose exact match is not a reference name
(`validite == "NR"`) is ignored rather than followed to its accepted
name; deliberately narrow, to extend if needed.
"""

from __future__ import annotations

import asyncio
import re

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author
from organon.modules.inpn.adapter import InpnAdapter
from organon.modules.inpn.ranks import KINGDOM_RANKS, inpn_lookup_kingdom, inpn_to_wp_rank

# Technical root of TAXREF (not a real taxon): always first in the
# breadcrumb, filtered before resolution rather than given a rank.
_ROOT_NAME = "Biota"

# TAXREF never indexes the "Genus (Subgenus)" notation: the subgenus is
# stored under its name alone (`lbNom`), identical to the genus for the
# nominotypical subgenus (e.g. "Eupelmus (Eupelmus)" is lbNom
# "Eupelmus", rank SSGN, next to the genus "Eupelmus", rank GN), so a
# literal search with parentheses finds nothing.
_SUBGENUS_RE = re.compile(r"^(?P<genre>\S+)\s*\((?P<sousgenre>\S+)\)$")


class InpnModule(TaxonomyModule):
    """INPN/TAXREF module."""

    meta = ModuleMeta(
        id="inpn", can_classify=True, can_render_external_link=True, domains="all", priority=500
    )

    def __init__(self, adapter: InpnAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or InpnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from TAXREF."""
        adapter = self._adapter
        taxon = struct.taxon.name

        subgenus = _SUBGENUS_RE.match(taxon)
        search_name = subgenus.group("sousgenre") if subgenus else taxon

        def _rank_matches(r: dict) -> bool:
            # Without parentheses in the query, drop the nominotypical
            # subgenus homonymous with the genus (same lbNom, rank SSGN)
            # so it is never picked instead of the genus; with
            # parentheses, require that SSGN rank.
            code = (r.get("rang") or {}).get("rang")
            return code == "SSGN" if subgenus else code != "SSGN"

        results = await adapter.search(search_name)
        match = next(
            (
                r
                for r in results
                if r.get("lbNom") == search_name and r.get("validite") == "NR" and _rank_matches(r)
            ),
            None,
        )
        if match is None or not match.get("cdNom"):
            return None

        cd_nom = match["cdNom"]
        author = format_author(match.get("lbAuteur"))

        struct.links["inpn"] = {"id": cd_nom, "name": taxon}
        if author:
            struct.links["inpn"]["author"] = author

        html = await adapter.detail_html(cd_nom)
        vernacular = adapter.parse_vernacular_french(html)
        if vernacular:
            struct.vernacular["INPN"] = {"fr": vernacular}

        if not is_classification:
            return struct

        rank_code = (match.get("rang") or {}).get("rang")
        wp_rank = inpn_to_wp_rank(rank_code or "")
        if wp_rank is None:
            return None
        struct.taxon.rank = wp_rank
        if author:
            struct.taxon.author = author

        ancestors = [
            (aid, name) for aid, name in adapter.parse_breadcrumb(html) if name != _ROOT_NAME
        ]
        ancestor_results = await asyncio.gather(*(adapter.search(name) for _, name in ancestors))

        ranks: list[RankName] = []
        kingdom_name: str | None = None
        for (ancestor_id, ancestor_name), ancestor_matches in zip(
            ancestors, ancestor_results, strict=True
        ):
            ancestor_match = next(
                (
                    r
                    for r in ancestor_matches
                    if r.get("cdNom") == ancestor_id and r.get("lbNom") == ancestor_name
                ),
                None,
            )
            if ancestor_match is None:
                continue
            ancestor_wp_rank = inpn_to_wp_rank(
                (ancestor_match.get("rang") or {}).get("rang") or ""
            )
            if ancestor_wp_rank == "règne":
                kingdom_name = ancestor_name
                continue
            if ancestor_wp_rank is None or ancestor_wp_rank in KINGDOM_RANKS:
                continue
            ranks.append(
                RankName(
                    name=ancestor_name,
                    rank=ancestor_wp_rank,
                    author=format_author(ancestor_match.get("lbAuteur")),
                )
            )
        ranks.reverse()  # breadcrumb is root to leaf; struct.ranks wants nearest first
        struct.ranks = ranks

        if kingdom_name:
            struct.kingdom = inpn_lookup_kingdom(kingdom_name)

        struct.classification = "TAXREF"
        struct.classification_taxobox = "inpn"
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{INPN}} template."""
        data = struct.links.get("inpn")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            target += " " + author
        return f"{{{{INPN | {data['id']} | {target} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the TAXREF page."""
        data = struct.links.get("inpn")
        if not data or "id" not in data:
            return None
        return (
            f"<a href='https://taxref.mnhn.fr/taxref-web/taxa/{data['id']}' target='_blank' "
            f"rel='noopener noreferrer'>INPN</a>"
        )


register_module(InpnModule)
