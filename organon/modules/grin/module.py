"""GRIN Taxonomy (Germplasm Resources Information Network, USDA).

Classification of cultivated plants and genetic resources through
ChecklistBank dataset 2018. Domain `végétal` (no dedicated subdomain in
the Organon tree): a taxon out of scope is simply absent, and `collect`
returns None.

Like `organon.modules.bryonames.module`, this dataset is single-source
and curated by one editor: no multi-candidate disambiguation
(`select_col_xr_candidate`) is needed, the first "accepted" candidate of
`type=EXACT` is enough.

The kingdom is never deduced from `classification`: the chain has no
`kingdom`, `order` or `class` rank (it starts at `family`), so
`struct.kingdom` is fixed to `"végétal"` once a candidate is validated,
as `bryonames` does.

Unlike Bryonames, GRIN has real dedicated `{{Bioref}}` templates on
frwiki, one per rank (`{{GRIN espèce}}`, genre, sous-tribu, tribu,
sous-famille, famille); `render_bioref` picks one by rank, as
`indexfungorum` does. `codeGRIN` (parameter 1) is the raw numeric id on
npgsweb.ars-grin.gov; ChecklistBank prefixes it by rank group (`gen:` or
`fam:`), and removing the prefix restores it.

`{{GRIN espèce}}` has no positional "validity" (`nv`) parameter, so
`render_bioref` falls back on the same `<small>(non valide)</small>`
suffix as `bryonames` for that rank only.

`debug_link` cannot use a single URL pattern: `name.link` is returned
only at species rank, so `_grin_url` rebuilds the URL per rank from the
scheme of the wiki templates.
"""

from __future__ import annotations

from functools import partial

from organon.core.config import GenerateOptions
from organon.core.models import (
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.checklistbank import ChecklistBankAdapter
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.common import (
    as_limit,
    checklistbank_accepted_name,
    collect_pages,
    follow_synonym,
    format_author,
)

# Ranks mapped to `{{GRIN espèce}}`; the others in this dataset (family
# and below) each have their own template.
_SPECIES_RANKS = {"espèce", "sous-espèce", "variété", "forme"}

# Any rank absent here falls back on `{{GRIN famille}}`: the GRIN chain
# never goes above the family, which is the default template.
_TEMPLATE_BY_RANK = {
    "sous-tribu": "GRIN sous-tribu",
    "tribu": "GRIN tribu",
    "sous-famille": "GRIN sous-famille",
    "genre": "GRIN genre",
}


def _template_for_rank(rank: str) -> str:
    """Return the {{GRIN ...}} template name for a rank."""
    if rank in _SPECIES_RANKS:
        return "GRIN espèce"
    return _TEMPLATE_BY_RANK.get(rank, "GRIN famille")


def _grin_code(taxon_id: str) -> str:
    """Return the raw GRIN code of a ChecklistBank id."""
    return taxon_id.rsplit(":", 1)[-1]


# GRIN serves family, subfamily, tribe and subtribe through one
# `taxonomyfamily.aspx` page told apart by `type=`, while species and
# genus have their own pages. Scheme taken from the six templates and
# reused by `debug_link`, `name.link` being returned at species rank
# only.
_URL_TYPE = {
    "GRIN sous-tribu": "subtribe",
    "GRIN tribu": "tribe",
    "GRIN sous-famille": "subfamily",
    "GRIN famille": "family",
}


def _grin_url(rank: str, code: str) -> str:
    """Return the GRIN site URL of a taxon, by rank."""
    template = _template_for_rank(rank)
    if template == "GRIN espèce":
        return f"https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomydetail?id={code}"
    if template == "GRIN genre":
        return f"https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomygenus.aspx?id={code}"
    return (
        "https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomyfamily.aspx"
        f"?type={_URL_TYPE[template]}&id={code}"
    )


class GrinModule(TaxonomyModule):
    """GRIN Taxonomy module."""

    meta = ModuleMeta(
        id="grin",
        can_classify=True,
        can_render_external_link=True,
        domains=["végétal"],
    )

    def __init__(self, adapter: ChecklistBankAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or ChecklistBankAdapter("2018")

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from GRIN."""
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        """Collect with a synonym hop count."""
        adapter = self._adapter

        candidates = await adapter.search(struct.taxon.name)
        if not candidates:
            return None

        accepted = [r for r in candidates if r["usage"]["status"] == "accepted"]
        cur = accepted[0] if accepted else None
        if cur is None:
            if not options.follow_synonyms:
                return None
            cur = candidates[0]

        usage = cur["usage"]
        name = usage["name"]
        taxon_id = cur["id"]

        struct.links["grin"] = {
            "id": taxon_id,
            "name": name["scientificName"],
            "author": format_author(name.get("authorship")),
            "rank": col_xr_to_wp_rank(name["rank"]),
            "link": name.get("link"),
        }

        is_synonym = usage["status"] == "synonym"
        struct.links["grin"]["detected_status"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            handled, result = await follow_synonym(
                struct,
                "grin",
                is_classification,
                options,
                hop,
                partial(checklistbank_accepted_name, usage),
                lambda next_hop: self._collect(struct, is_classification, options, hop=next_hop),
            )
            if handled:
                return result

        if not is_classification:
            return struct

        struct.taxon.author = format_author(name.get("authorship"))
        struct.taxon.rank = col_xr_to_wp_rank(name["rank"])
        struct.taxon.name = name["scientificName"].strip()
        struct.classification = "GRIN"
        struct.classification_taxobox = "GRIN"
        struct.kingdom = "végétal"

        classification = cur.get("classification", [])
        struct.ranks = [
            RankName(
                name=c["name"],
                rank=col_xr_to_wp_rank(c["rank"]),
                author=format_author(c.get("authorship")),
            )
            for c in reversed(classification)
            if c.get("id") != taxon_id
        ]

        async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.children_page(taxon_id, offset)
            raw = page.get("result", [])
            out = []
            for c in raw:
                if c.get("rank") == "unranked" or c.get("status") != "accepted":
                    continue
                out.append(
                    RankName(
                        name=c["name"],
                        rank=col_xr_to_wp_rank(c["rank"]),
                        author=format_author(c.get("authorship")),
                    )
                )
            return out, len(raw), page.get("last", True)

        items, truncated = await collect_pages(fetch_children, limit=as_limit(options.list_limit))
        if items:
            struct.subtaxa = SubTaxonList(items=items, source="GRIN", truncated=truncated)

        syn = await adapter.synonyms(taxon_id)
        synonyms = []
        for entry in [*syn.get("homotypic", []), *syn.get("heterotypic", [])]:
            sname = entry.get("name") or {}
            if not sname.get("scientificName"):
                continue
            synonyms.append(
                RankName(
                    name=sname["scientificName"],
                    author=format_author(sname.get("authorship")),
                    rank=col_xr_to_wp_rank(sname.get("rank", "")),
                )
            )
        if synonyms:
            struct.synonyms = SynonymList(items=synonyms, source="GRIN", truncated=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{GRIN ...}} template of the rank."""
        data = struct.links.get("grin")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        rank = data.get("rank") or struct.taxon.rank or ""
        template = _template_for_rank(rank)
        code = _grin_code(str(data["id"]))
        target = wp_apply_italics(data["name"], rank, struct.kingdom)
        if author := data.get("author"):
            target += " " + author

        if template == "GRIN espèce":
            post = " <small>(non valide)</small>" if data.get("synonym") else ""
            return f"{{{{{template} | {code} | {target} | consulté le={cdate} }}}}{post}"

        fields = [code, target]
        if data.get("synonym"):
            fields.append("nv")
        body = " | ".join(fields)
        return f"{{{{{template} | {body} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the GRIN page."""
        data = struct.links.get("grin")
        if not data or "id" not in data:
            return None
        rank = data.get("rank") or struct.taxon.rank or ""
        url = data.get("link") or _grin_url(rank, _grin_code(str(data["id"])))
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>GRIN</a>"


register_module(GrinModule)
