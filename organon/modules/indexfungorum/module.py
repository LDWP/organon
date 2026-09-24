"""Index Fungorum module: fungal classification (domain `champignon`).

The service has a real `.asmx` webservice with an `HttpGet` binding (see
adapter.py).

`NameSearch` returns neither the publication fields nor the
classification chain: a second `NameByKey` call is always needed. That
chain is joined only for genus rank and below; a family or higher search
is insufficient data (`collect` returns None when classifying), not an
error.

Accepted name: among the exact matches on `NAME_OF_FUNGUS`, the accepted
record is the one whose `CURRENT_NAME_RECORD_NUMBER` equals its own
`RECORD_NUMBER`; otherwise follow it via `NameByKey` to that
self-reference, bounded by `MAX_SYNONYM_HOPS`.

`NamesByCurrentKey` gives a real, unpaginated synonym list, truncated by
hand per `limite-listes`. The service exposes no vernacular names or
sub-taxa.
"""

from __future__ import annotations

import asyncio

from organon.core.config import GenerateOptions
from organon.core.models import Basionym, LinkEntry, RankName, Struct, SynonymList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import (
    MAX_SYNONYM_HOPS,
    as_limit,
    format_author,
    format_author_year,
    simple_debug_link,
)
from organon.modules.indexfungorum.adapter import IndexFungorumAdapter
from organon.modules.indexfungorum.ranks import (
    CLASSIFICATION_LADDER,
    UNRESOLVED_PLACEHOLDER,
    indexfungorum_to_wp_rank,
    ixf_kingdom,
)

MAX_NUMBER = 50

# Ranks mapped to `{{Fungorum espèce}}`; genus and family have their own
# template, anything above the family uses `{{Fungorum suprafamille}}`.
_SPECIES_RANKS = {"espèce", "sous-espèce", "variété", "forme"}


class IndexFungorumModule(TaxonomyModule):
    """Index Fungorum module."""

    meta = ModuleMeta(
        id="indexfungorum",
        can_classify=True,
        can_render_external_link=True,
        domains=["champignon"],
    )

    def __init__(self, adapter: IndexFungorumAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or IndexFungorumAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from Index Fungorum."""
        records = await self._adapter.name_search(struct.taxon.name, max_number=MAX_NUMBER)
        exact = [r for r in records if r.get("NAME_OF_FUNGUS") == struct.taxon.name]
        if not exact:
            return None

        accepted_hit = next(
            (r for r in exact if r.get("CURRENT_NAME_RECORD_NUMBER") == r.get("RECORD_NUMBER")),
            None,
        )
        if accepted_hit is not None:
            full = await self._adapter.name_by_key(accepted_hit["RECORD_NUMBER"])
        else:
            # Variant outside `follow_synonym`: the synonym chain is
            # followed by an iterative loop (no recursion) before
            # `links` is built.
            if not options.follow_synonyms:
                return None
            full = await self._adapter.name_by_key(exact[0]["RECORD_NUMBER"])
            hop = 0
            while (
                full is not None
                and full.get("CURRENT_NAME_RECORD_NUMBER")
                and full["CURRENT_NAME_RECORD_NUMBER"] != full["RECORD_NUMBER"]
            ):
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                full = await self._adapter.name_by_key(full["CURRENT_NAME_RECORD_NUMBER"])
                hop += 1
        if full is None:
            return None

        is_redirect = full["NAME_OF_FUNGUS"] != struct.taxon.name

        # `AUTHORS` alone has no publication year (ICN convention, like
        # POWO, IPNI, AlgaeBase): `YEAR_OF_PUBLICATION`, only on
        # `NameByKey`, provides it.
        author_year = format_author_year(full.get("AUTHORS"), full.get("YEAR_OF_PUBLICATION"))
        ixf_link: LinkEntry = {
            "id": full["RECORD_NUMBER"],
            "name": full["NAME_OF_FUNGUS"],
            "rank": indexfungorum_to_wp_rank(full.get("INFRASPECIFIC_RANK")),
            "author": format_author(author_year),
        }
        if is_redirect:
            ixf_link["synonym"] = True
        struct.links["indexfungorum"] = ixf_link

        if is_redirect:
            if not is_classification:
                return struct
            if not options.follow_synonyms:
                return struct
            struct.taxon = TaxonInfo(name=full["NAME_OF_FUNGUS"])

        if not is_classification:
            return struct

        if not full.get("Genus_name"):
            return None  # family and above: NameByKey joins no hierarchy

        kingdom = ixf_kingdom(full.get("Kingdom_name"))
        if kingdom is None:
            return None  # no Kingdom_name: insufficient classification data
        struct.kingdom = kingdom
        struct.taxon.rank = indexfungorum_to_wp_rank(full.get("INFRASPECIFIC_RANK"))
        struct.taxon.author = format_author(author_year)

        # IF and SF share one backend and RecordID but not their role:
        # IF is a plain directory of published names (render_bioref and
        # debug_link stay on "Index Fungorum"), while SF is the
        # authority on correct name vs synonym, hence "Species Fungorum"
        # for the classification. "speciesfungorum" is the proposed
        # Bioref key; Modèle:Bioref/switch has no such entry yet and the
        # wiki template must be created.
        struct.classification = "speciesfungorum"
        struct.classification_taxobox = "Species Fungorum"

        ranks: list[RankName] = []
        for field, french_rank in CLASSIFICATION_LADDER:
            value = full.get(field)
            if not value or value == UNRESOLVED_PLACEHOLDER or value == full["NAME_OF_FUNGUS"]:
                continue
            ranks.append(RankName(name=value, rank=french_rank))
        struct.ranks = ranks

        # `name_by_key` (basionym) and `names_by_current_key` (synonyms)
        # depend only on `full`: run in parallel.
        basionym_id = full.get("BASIONYM_RECORD_NUMBER")
        if basionym_id and basionym_id != full["RECORD_NUMBER"]:
            basionym, synonym_records = await asyncio.gather(
                self._adapter.name_by_key(basionym_id),
                self._adapter.names_by_current_key(full["RECORD_NUMBER"]),
            )
            if basionym is not None:
                struct.basionym = Basionym(
                    name=basionym["NAME_OF_FUNGUS"],
                    author=format_author(basionym.get("AUTHORS")),
                    source="Index Fungorum",
                )
        else:
            synonym_records = await self._adapter.names_by_current_key(full["RECORD_NUMBER"])
        synonyms = [
            RankName(
                name=s["NAME_OF_FUNGUS"],
                author=format_author(s.get("AUTHORS")),
                rank=indexfungorum_to_wp_rank(s.get("INFRASPECIFIC_RANK")),
            )
            for s in synonym_records
            if s.get("RECORD_NUMBER") != full["RECORD_NUMBER"]
        ]
        if synonyms:
            limit = as_limit(options.list_limit)
            truncated = limit is not None and len(synonyms) > limit
            struct.synonyms = SynonymList(
                items=synonyms[:limit] if truncated else synonyms,
                source="Index Fungorum",
                truncated=truncated,
            )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render one of four rank-specific {{Fungorum ...}} templates.

        Species, genus, family, and anything above the family. Same
        positional signature: `id | name | author | validity`. The name
        is not italicized: the template does it.
        """
        data = struct.links.get("indexfungorum")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        rank = data.get("rank") or struct.taxon.rank
        if rank in _SPECIES_RANKS:
            template = "Fungorum espèce"
        elif rank == "genre":
            template = "Fungorum genre"
        elif rank == "famille":
            template = "Fungorum famille"
        else:
            template = "Fungorum suprafamille"
        author = data.get("author") or ""
        validity = "nv" if data.get("synonym") else ""
        fields = [str(data["id"]), data["name"]]
        if author or validity:
            fields.append(author)
        if validity:
            fields.append(validity)
        body = " | ".join(fields)
        return f"{{{{{template} | {body} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the Index Fungorum record."""
        return simple_debug_link(
            struct,
            "indexfungorum",
            "http://www.indexfungorum.org/names/NamesRecord.asp?RecordID={id}",
            "Index Fungorum",
        )


register_module(IndexFungorumModule)
