"""Hesperomys module: mammal taxonomy, classification and synonyms.

Makes no HTTP call itself; see adapter.py.

No synonym following: `taxonByLabel` resolves only valid taxa, so a
synonym given as input returns None, like an absent name.

Domain restricted to `mammifère`: `class_.validName` (or the taxon's own
name if it is the class) must be "Mammalia" when classifying, else give
up.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, RankName, Struct, SynonymList
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.common import as_limit, format_author, simple_debug_link
from organon.modules.hesperomys.adapter import HesperomysAdapter
from organon.modules.hesperomys.ranks import hesperomys_to_wp_rank

_AGE_EXTANT = "extant"
_AGE_INVALID = {"removed", "redirect"}


def _author_string(author_tags: list[dict] | None) -> str | None:
    """Return the author names of the tags, abbreviated beyond three."""
    names = [
        t["person"]["familyName"]
        for t in (author_tags or [])
        if t.get("__typename") == "Author" and t.get("person", {}).get("familyName")
    ]
    if not names:
        return None
    if len(names) > 3:
        return f"{names[0]} et al."
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " & " + names[-1]


def _year(value: str | None) -> str | None:
    """Return the year of a date.

    `year` comes as a full ISO date ("1758-01-01") or a bare year
    ("1829"); only the year is used.
    """
    if not value:
        return None
    return value.split("-", 1)[0]


def _citation(base_name: dict | None) -> str | None:
    """Return "Author, Year" for a base name, or None.

    The format struct.taxon.author and RankName.author expect.
    """
    if not base_name:
        return None
    author = _author_string(base_name.get("authorTags"))
    year = _year(base_name.get("year"))
    if author and year:
        return format_author(f"{author}, {year}")
    return format_author(author or year)


def _is_extinct(age: str | None) -> bool | None:
    """Return whether the age says extinct, None if unknown."""
    if not age:
        return None
    return age != _AGE_EXTANT


class HesperomysModule(TaxonomyModule):
    """Hesperomys module."""

    meta = ModuleMeta(
        id="hesperomys", can_classify=True, can_render_external_link=False, domains=["mammifère"]
    )

    def __init__(self, adapter: HesperomysAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or HesperomysAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from Hesperomys."""
        adapter = self._adapter
        name = struct.taxon.name

        results = await adapter.taxon_by_label(name)
        exact = [r for r in results if r.get("validName") == name]
        if not exact:
            return None
        match = exact[0]

        detail = await adapter.taxon_detail(match["oid"])
        if detail is None:
            return None

        age = detail.get("age")
        if age in _AGE_INVALID:
            return None

        rank = hesperomys_to_wp_rank(detail.get("rank"))
        entry: LinkEntry = {"id": detail["oid"], "name": detail["validName"]}
        citation = _citation(detail.get("baseName"))
        if citation:
            entry["author"] = citation
        if rank:
            entry["rank"] = rank
        extinct = _is_extinct(age)
        if extinct is not None:
            entry["extinct"] = extinct
        struct.links["hesperomys"] = entry

        if not is_classification:
            return struct

        class_ = detail.get("class_") or {}
        is_mammal = class_.get("validName") == "Mammalia" or detail.get("validName") == "Mammalia"
        if not is_mammal:
            return None

        struct.taxon.rank = rank
        struct.taxon.author = citation
        if extinct is not None:
            struct.taxon.extinct = extinct
        struct.kingdom = "animal"
        struct.classification = "Hesperomys"
        struct.classification_taxobox = "Hesperomys"

        ancestors = await adapter.ancestors(detail.get("parent"))
        ranks: list[RankName] = []
        for a in ancestors:
            ancestor_rank = hesperomys_to_wp_rank(a.get("rank"))
            if ancestor_rank is None:
                # Non-standard cladistic rank (e.g. "clade") with no
                # Wikipedia equivalent: excluded rather than leaking an
                # unknown rank (same as INPN).
                continue
            ranks.append(
                RankName(
                    name=a["validName"], rank=ancestor_rank, author=_citation(a.get("baseName"))
                )
            )
        struct.ranks = ranks

        limit = as_limit(options.list_limit)
        synonyms_list = [
            RankName(
                name=n.get("correctedOriginalName") or n.get("originalName") or n.get("rootName"),
                author=_citation(n),
                rank=hesperomys_to_wp_rank(n.get("originalRank")),
            )
            for n in (e["node"] for e in detail.get("names", {}).get("edges", []))
            if n.get("status") != "valid"
            and (n.get("correctedOriginalName") or n.get("originalName") or n.get("rootName"))
        ]
        truncated = False
        if limit is not None and len(synonyms_list) > limit:
            synonyms_list = synonyms_list[:limit]
            truncated = True
        if synonyms_list:
            struct.synonyms = SynonymList(
                items=synonyms_list, source="Hesperomys", truncated=truncated
            )

        return struct

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to Hesperomys."""
        return simple_debug_link(
            struct, "hesperomys", "https://hesperomys.com/t/{id}", "Hesperomys"
        )


register_module(HesperomysModule)
