"""POWO module: classification, synonyms, distribution, sub-taxa.

Domain `végétal`.

`search()` returns several records for an ambiguous name: filter on an
exact `name`, then prefer `accepted=True` (else the first exact match,
as `organon.modules.tropicos`). `lookup(id, include=['distribution'])`
then fetches the full record from the `fqId` (full IPNI LSID).

Synonym following (classification only): a record whose
`taxonomicStatus` is not "Accepted" carries an `accepted` field, used to
rerun the collection on that name if `follow_synonyms` is on; otherwise
the classification is built from the synonym itself.

Distribution: `detail["distribution"]` is a dict of categories
(`natives`, `introduced`, `absent`…), each entry carrying `tdwgCode` (a
WGSRPD level-3 code, e.g. "FRA") and `establishment`.
`_distribution_entries` drops "Absent", takes "Native" and "Introduced"
as certain, the rest as uncertain, and falls back on the flat
`locations` list. "Introduced" and "Extinct" are also isolated in their
own subsets for distinct {{WGSRPD}} colors.

These are not ISO 3166 codes: the Répartition text falls back on the raw
unlinked code, while `{{WGSRPD}}` uses them directly (see
`sections.render_distribution`).
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import (
    DistributionEntry,
    LinkEntry,
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
    TaxonInfo,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import (
    MAX_SYNONYM_HOPS,
    as_limit,
    format_author,
    format_author_year,
    simple_debug_link,
)
from organon.modules.powo.adapter import PowoAdapter
from organon.modules.powo.ranks import powo_lookup_kingdom, powo_to_wp_rank

_ABSENT = "absent"
_EXTINCT = "extinct"
_INTRODUCED = "introduced"
_UNCERTAIN = {"doubtful", _EXTINCT}


def _distribution_entries(
    detail: dict,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """Return (certain, uncertain, introduced, extinct) code dicts.

    `introduced` and `extinct` are subsets of the other two, isolating
    the codes whose POWO status is explicitly so (see
    `DistributionEntry`).
    """
    certain: dict[str, str] = {}
    uncertain: dict[str, str] = {}
    introduced: dict[str, str] = {}
    extinct: dict[str, str] = {}

    dist = detail.get("distribution")
    if isinstance(dist, dict):
        for entries in dist.values():
            if not isinstance(entries, list):
                continue
            for e in entries:
                code = e.get("tdwgCode")
                if not isinstance(code, str):
                    continue
                status = (e.get("establishment") or "").lower()
                if status == _ABSENT:
                    continue
                if status in _UNCERTAIN:
                    uncertain[code] = code
                    if status == _EXTINCT:
                        extinct[code] = code
                else:
                    certain[code] = code
                    if status == _INTRODUCED:
                        introduced[code] = code
        return certain, uncertain, introduced, extinct

    locations = detail.get("locations")
    if isinstance(locations, list):
        certain = {code: code for code in locations if isinstance(code, str)}
    return certain, uncertain, introduced, extinct


class PowoModule(TaxonomyModule):
    """POWO module."""

    meta = ModuleMeta(
        id="powo", can_classify=True, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: PowoAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or PowoAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from POWO."""
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        """Collect with a synonym hop count."""
        results = await self._adapter.search(struct.taxon.name)
        exact = [r for r in results if r.get("name") == struct.taxon.name]
        if not exact:
            return None
        match = next((r for r in exact if r.get("accepted")), exact[0])

        taxon_id = match.get("fqId")
        if not taxon_id:
            return None

        detail = await self._adapter.lookup(taxon_id, include=["distribution"])
        if detail is None:
            return None

        number = taxon_id.rsplit(":", 1)[-1]
        rank = powo_to_wp_rank(detail.get("rank"))
        author_year = format_author_year(detail.get("authors"), detail.get("namePublishedInYear"))
        entry: LinkEntry = {
            "id": number,
            "name": detail.get("name") or match["name"],
            "author": format_author(author_year),
        }
        if rank:
            entry["rank"] = rank
        is_synonym = detail.get("taxonomicStatus") not in (None, "Accepted")
        if is_synonym:
            entry["synonym"] = True
        struct.links["powo"] = entry

        synonyms_list = [
            RankName(
                name=s["name"],
                author=format_author(s.get("author")),
                rank=powo_to_wp_rank(s.get("rank")),
            )
            for s in detail.get("synonyms") or []
            if s.get("name")
        ]
        limit = as_limit(options.list_limit)
        truncated = False
        if limit is not None and len(synonyms_list) > limit:
            synonyms_list = synonyms_list[:limit]
            truncated = True
        if synonyms_list:
            struct.synonyms = SynonymList(items=synonyms_list, source="POWO", truncated=truncated)

        certain, uncertain, introduced, extinct = _distribution_entries(detail)
        if certain or uncertain:
            struct.distribution["powo"] = DistributionEntry(
                certain=certain, uncertain=uncertain, introduced=introduced, extinct=extinct
            )

        # Variant outside `follow_synonym`: the synonym is not marked in
        # `links` outside classification, and an unusable "accepted"
        # field falls back on the synonym itself.
        if is_synonym:
            if not is_classification:
                return struct
            if options.follow_synonyms:
                accepted = detail.get("accepted") or {}
                if accepted.get("fqId") and accepted.get("name"):
                    if hop >= MAX_SYNONYM_HOPS:
                        return None
                    struct.taxon = TaxonInfo(name=accepted["name"])
                    return await self._collect(struct, is_classification, options, hop=hop + 1)
            # follow_synonyms is off (or no usable "accepted" field):
            # keep going with the synonym as is, like ITIS and GBIF.

        if not is_classification:
            return struct

        kingdom = powo_lookup_kingdom(detail.get("kingdom"))
        if not kingdom:
            return None

        struct.taxon.rank = rank
        struct.taxon.author = format_author(author_year)
        struct.kingdom = kingdom
        struct.classification = "POWO"
        struct.classification_taxobox = "POWO"

        chain = detail.get("classification") or []
        ranks = [
            RankName(
                name=c["name"],
                rank=powo_to_wp_rank(c.get("rank")),
                author=format_author(c.get("author")),
            )
            for c in chain
            if c.get("fqId") != taxon_id and c.get("name")
        ]
        ranks.reverse()

        # `classification` only has family and genus (WCVP): the higher
        # ranks (phylum, class, subclass, order) are separate scalar
        # fields, or the POWO taxobox would stop at the family.
        for field, rank_code in (
            ("order", "ORDER"),
            ("subclass", "SUBCLASS"),
            ("clazz", "CLASS"),
            ("phylum", "PHYLUM"),
        ):
            name = detail.get(field)
            if name:
                ranks.append(RankName(name=name, rank=powo_to_wp_rank(rank_code)))

        struct.ranks = ranks

        children = [
            c
            for c in detail.get("childNameUsages") or []
            if c.get("name") and c.get("taxonomicStatus") == "Accepted"
        ]
        if children:
            limit = as_limit(options.list_limit)
            truncated = False
            if limit is not None and len(children) > limit:
                children = children[:limit]
                truncated = True
            struct.subtaxa = SubTaxonList(
                items=[
                    RankName(
                        name=c["name"],
                        author=format_author(c.get("author")),
                        rank=powo_to_wp_rank(c.get("rank")),
                    )
                    for c in children
                ],
                source="POWO",
                truncated=truncated,
            )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{POWO}} template."""
        data = struct.links.get("powo")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        parts = [str(data["id"]), data["name"]]
        if data.get("author") or data.get("synonym"):
            parts.append(data.get("author") or "")
        if data.get("synonym"):
            parts.append("nv")
        body = " | ".join(parts)
        return f"{{{{POWO | {body} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the POWO page."""
        return simple_debug_link(
            struct,
            "powo",
            "https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:{id}",
            "POWO",
        )


register_module(PowoModule)
