"""ITIS module: classification, synonyms, sub-taxa, vernacular names.

Synonym following reruns the collection on the target taxon in the same
mode (full classification or links only).
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.langues import groupe_par_langue
from organon.core.models import RankName, Struct, SubTaxonList, SynonymList
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import follow_synonym, format_author, simple_debug_link
from organon.modules.itis.adapter import ItisAdapter
from organon.modules.itis.ranks import KINGDOM_RANKS, itis_lookup_kingdom, itis_to_wp_rank


class ItisModule(TaxonomyModule):
    """ITIS module."""

    meta = ModuleMeta(
        id="itis", can_classify=True, can_render_external_link=True, domains="all", priority=998
    )

    def __init__(self, adapter: ItisAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or ItisAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from ITIS."""
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        """Collect with a synonym hop count."""
        adapter = self._adapter
        taxon = struct.taxon.name

        results = await adapter.search_by_scientific_name(taxon)
        if not results:
            return None

        # `searchByScientificName` is fuzzy (e.g. "Boletus" returns
        # species whose epithet is "boletus" in other genera, across
        # kingdoms): without this filter `results[0]` may be an
        # unrelated homonym with a wrong kingdom.
        candidates = [sn for sn in results if sn.get("combinedName") == taxon]
        if not candidates:
            return None
        match, accepted_prefetched = await self._resolve_homonym(candidates, adapter)
        if match is None or not match.get("tsn"):
            return None
        tsn = match["tsn"]

        if is_classification and match.get("kingdom"):
            struct.kingdom = itis_lookup_kingdom(match["kingdom"])

        struct.links["itis"] = {"id": tsn, "name": match.get("combinedName") or taxon}
        if match.get("author"):
            struct.links["itis"]["author"] = format_author(match["author"])
        if not is_classification and match.get("kingdom"):
            # Kingdom signal detected with no extra call: "kingdom" is
            # already in the search response. See KingdomInconsistency.
            detected_kingdom = itis_lookup_kingdom(match["kingdom"])
            if detected_kingdom:
                struct.links["itis"]["detected_kingdom"] = detected_kingdom

        if accepted_prefetched is not None:
            accepted = accepted_prefetched
        else:
            accepted = await adapter.accepted_names(tsn)
        accepted_entry = next((a for a in accepted if a.get("acceptedName")), None)
        if accepted_entry is not None:
            if not is_classification:
                struct.links["itis"]["synonym_name"] = accepted_entry["acceptedName"]
                struct.links["itis"]["synonym_id"] = accepted_entry.get("acceptedTsn")

            async def resolve_accepted() -> str | None:
                return accepted_entry["acceptedName"]

            handled, result = await follow_synonym(
                struct,
                "itis",
                is_classification,
                options,
                hop,
                resolve_accepted,
                lambda next_hop: self._collect(struct, is_classification, options, hop=next_hop),
            )
            if handled:
                return result
            # follow_synonyms is off: keep going with the synonym as is

        if not is_classification:
            return struct

        rank = await adapter.rank_name(tsn)
        if rank is None:
            return None
        author = await adapter.authorship(tsn)

        if author:
            struct.taxon.author = format_author(author)
        struct.taxon.rank = itis_to_wp_rank(rank)
        struct.classification = "ITIS"
        struct.classification_taxobox = "itis"

        hierarchy = await adapter.full_hierarchy(tsn)
        ranks: list[RankName] = []
        for entry in hierarchy:
            if entry.get("tsn") == tsn:
                # The requested taxon ends the ancestor chain.
                # `getFullHierarchyFromTSN` also includes its direct
                # children below it: stop here so they stay out of the
                # classification.
                break
            if not entry.get("taxonName"):
                continue
            wp_rank = itis_to_wp_rank(entry.get("rankName") or "")
            if wp_rank in KINGDOM_RANKS:
                continue  # the kingdom is stored in struct.kingdom, not struct.ranks
            ranks.append(
                RankName(
                    name=entry["taxonName"],
                    rank=wp_rank,
                    author=format_author(entry.get("author")),
                )
            )
        ranks.reverse()  # ITIS answers root to leaf; we want nearest first
        struct.ranks = ranks

        children = await adapter.hierarchy_down(tsn)
        subtaxa_list = [
            RankName(
                name=c["taxonName"],
                author=format_author(c.get("author")),
                rank=itis_to_wp_rank(c["rankName"]) if c.get("rankName") else None,
            )
            for c in children
            if c.get("taxonName")
        ]
        if subtaxa_list:
            struct.subtaxa = SubTaxonList(items=subtaxa_list, source="ITIS")

        synonyms = await adapter.synonym_names(tsn)
        synonym_list = [
            RankName(name=s["sciName"], author=format_author(s.get("author"))) for s in synonyms
        ]
        if synonym_list:
            struct.synonyms = SynonymList(items=synonym_list, source="ITIS")

        common = await adapter.common_names(tsn)
        vernacular = groupe_par_langue((c.get("language"), c.get("commonName")) for c in common)
        if vernacular:
            struct.vernacular["ITIS"] = vernacular

        return struct

    @staticmethod
    async def _resolve_homonym(
        candidates: list[dict], adapter: ItisAdapter
    ) -> tuple[dict, list[dict] | None]:
        """Pick one among entries with the same `combinedName`.

        E.g. "Aegilops tauschii" exists as a valid name and as a
        rejected or misapplied one under other authors. Without
        arbitration, an invalid homonym first in the results would be
        taken for the taxon. Prefer the first homonym that is itself the
        accepted name; if all are synonyms, take the first result.
        Return (entry, its accepted names or None).
        """
        if len(candidates) == 1:
            return candidates[0], None
        first_accepted: list[dict] | None = None
        for index, candidate in enumerate(candidates):
            tsn = candidate.get("tsn")
            if not tsn:
                continue
            accepted = await adapter.accepted_names(tsn)
            if index == 0:
                first_accepted = accepted
            if not any(a.get("acceptedName") for a in accepted):
                return candidate, accepted
        return candidates[0], first_accepted

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{ITIS}} template."""
        data = struct.links.get("itis")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        target = wp_apply_italics(data["name"], struct.taxon.rank, struct.kingdom)
        if author := data.get("author"):
            target += " " + author
        if data.get("synonym"):
            return f"{{{{ITIS | {data['id']} | {target} | nv | consulté le={cdate} }}}}"
        return f"{{{{ITIS | {data['id']} | {target} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the ITIS page."""
        return simple_debug_link(
            struct,
            "itis",
            "https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value={id}",
            "ITIS",
        )


register_module(ItisModule)
