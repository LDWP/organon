"""GBIF module: classification, synonyms, sub-taxa, vernacular names.

Makes no HTTP call itself; see adapter.py.
"""

from __future__ import annotations

import html as _html
import re

from organon.core.config import GenerateOptions
from organon.core.langues import groupe_par_langue
from organon.core.models import (
    Basionym,
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.authors import BOTANIST_KINGDOMS
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.bibliography import citation_or_text
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.lookup import find_col_xr_link
from organon.modules.common import (
    as_limit,
    collect_pages,
    follow_synonym,
    format_author,
    simple_debug_link,
)
from organon.modules.gbif.adapter import GbifAdapter
from organon.modules.gbif.ranks import (
    GBIF_MARKERS,
    GBIF_WP,
    gbif_lookup_kingdom,
    gbif_marker_to_rank,
    gbif_to_wp_rank,
)

_PUBLICATION_YEAR_RE = re.compile(r"\b(1[3-9]\d\d|20\d\d)\b")


def _probable_year(published_in: str | None, kingdom: str | None) -> int | None:
    """Extract a candidate publication year from `publishedIn`.

    GBIF has no structured year field. Limited to the ICN kingdoms
    (`BOTANIST_KINGDOMS`), where the author citation omits the year;
    zoology already carries it in `authorship`. Take the last plausible
    4-digit number. An imperfect extraction is harmless: the candidate
    is only used when another module confirms it (see
    `coherence.gbif_probable_year_validated`).
    """
    if not published_in or kingdom not in BOTANIST_KINGDOMS:
        return None
    matches = _PUBLICATION_YEAR_RE.findall(published_in)
    return int(matches[-1]) if matches else None


def _extract_rank_marker(name: str) -> tuple[str | None, str]:
    """Split an explicit infraspecific rank marker off a searched name.

    E.g. "subsp." in "Mentha spicata subsp. spicata". Return (matching
    GBIF rank, name without marker). `/species?name=` indexes these taxa
    without their marker: with it nothing matches, without it the match
    is ambiguous with other infraspecific variations, hence the rank.
    """
    words = name.split()
    for i, word in enumerate(words):
        rank = GBIF_MARKERS.get(word)
        if rank:
            return rank, " ".join(words[:i] + words[i + 1 :])
    return None, name


def _filter_rank_marker(expected_rank: str | None, candidates: list[dict]) -> list[dict]:
    """Keep the candidates whose GBIF rank matches the marker's rank.

    Without this the first homonym won, silently giving the wrong rank.
    """
    if expected_rank is None or len(candidates) < 2:
        return candidates
    filters = [r for r in candidates if r.get("rank") == expected_rank]
    return filters or candidates


async def _taxon_info(adapter: GbifAdapter, key: int) -> dict | None:
    """Return name, author, rank and extinction of a GBIF key."""
    name = await adapter.name_info(key)
    if name is None:
        return None
    canonical_name = name.get("canonicalNameWithMarker") or name.get("canonicalName")
    complete_name = name.get("canonicalNameComplete")
    if canonical_name is not None and complete_name is not None:
        author = complete_name[len(canonical_name) + 1 :]
    else:
        # GBIF does not split every name into canonical name and author
        # (`"parsed": false`), notably virus names. Fall back on the raw
        # scientific name rather than give up.
        canonical_name = name.get("scientificName")
        if canonical_name is None:
            return None
        author = ""

    result: dict = {"name": canonical_name, "author": author}
    if name.get("rank"):
        result["rank"] = gbif_to_wp_rank(name["rank"])
    elif name.get("rankMarker"):
        buf = gbif_marker_to_rank(name["rankMarker"])
        if buf is not None:
            result["rank"] = gbif_to_wp_rank(buf)

    profiles = await adapter.species_profiles(key)
    for p in profiles:
        if "extinct" in p:
            result["extinct"] = p["extinct"]
            break

    return result


class GbifModule(TaxonomyModule):
    """GBIF module."""

    meta = ModuleMeta(
        id="gbif",
        can_classify=True,
        can_render_external_link=True,
        domains="all",
        # Priority below COL: classifies only with the raw fields of the
        # legacy Backbone Taxonomy, never corrected by CoL XR. Still the
        # only classifier for a taxon absent from CoL XR.
        priority=200,
    )

    def __init__(
        self, adapter: GbifAdapter | None = None, col_xr_adapter: ColXrAdapter | None = None
    ) -> None:
        """Use the given adapters, else create them."""
        self._adapter = adapter or GbifAdapter()
        self._col_xr_adapter = col_xr_adapter or ColXrAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from GBIF."""
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        """Collect with a synonym hop count."""
        adapter = self._adapter

        # An already resolved id (e.g. chosen in the disambiguation
        # list, see `SearchMatch.gbif_key`) names a precise record: use
        # it rather than a fuzzy name search that may land elsewhere.
        # First call only (hop 0): a redirect to an accepted synonym
        # must resolve on its own name.
        cur: dict | None = None
        if hop == 0 and options.gbif_key is not None:
            cur = await adapter.species_record(options.gbif_key)

        if cur is None:
            marker_rank, name_without_marker = _extract_rank_marker(struct.taxon.name)
            results = await adapter.search(struct.taxon.name)
            if not results and marker_rank is not None:
                # `/species?name=` matches nothing with the botanical
                # infraspecific marker (e.g. "subsp."): retry without
                # it. The extracted rank then breaks ties.
                results = await adapter.search(name_without_marker)
            if not results:
                return None

            def _kingdom_matches(r: dict) -> bool:
                if struct.domain in ("*", ""):
                    return True
                return gbif_lookup_kingdom(r.get("kingdom", "")) == struct.domain

            accepted = [r for r in results if r.get("taxonomicStatus") == "ACCEPTED"]
            # A name can denote distinct taxa across kingdoms (e.g.
            # "Morus"): with a domain filter, prefer the entry whose
            # kingdom matches.
            candidates = [r for r in accepted if _kingdom_matches(r)] or accepted
            candidates = _filter_rank_marker(marker_rank, candidates)
            cur = candidates[0] if candidates else None
            if cur is None:
                if not options.follow_synonyms:
                    return None
                fallback = [r for r in results if _kingdom_matches(r)] or results
                cur = _filter_rank_marker(marker_rank, fallback)[0]

        key = cur["key"]
        info = await _taxon_info(adapter, key)
        if info is None:
            return None

        # COL XR (ChecklistBank 3LXR) has been the GBIF default taxonomy
        # since 2024: when the name resolves there, its alphanumeric id
        # replaces the numeric GBIF key for rendering (the template
        # accepts both). The numeric `key` still drives every GBIF call.
        col_xr = await find_col_xr_link(self._col_xr_adapter, info["name"], struct.domain)

        struct.links["gbif"] = {
            "id": col_xr.id if col_xr is not None else key,
            # Legacy key always kept: `id` may be a COL XR id (P14607),
            # the numeric key stays that of P846.
            "key": key,
            "author": format_author(info["author"]),
            "name": info["name"],
            **({"rank": info["rank"]} if "rank" in info else {}),
            **({"extinct": info["extinct"]} if "extinct" in info else {}),
        }
        if col_xr is not None:
            # COL XR record of the id above: only used for the second
            # {{CatalogueofLife}} link, not {{GBIF}}. Otherwise that
            # link cited the GBIF backbone author, giving two differing
            # lines that `compute_ext_link_items` would not merge when
            # `ColModule` resolves the same record.
            struct.links["gbif"]["col_xr"] = {
                "name": col_xr.nom,
                "author": col_xr.auteur,
                "rank": col_xr.rang,
                "extinct": col_xr.eteint,
            }
        if cur.get("publishedIn"):
            # Bibliographic citation already in the search response (no
            # extra call), like AlgaeBase's; no structured year field
            # unlike POWO, IPNI or Index Fungorum.
            struct.original_publication = await citation_or_text(
                adapter.resolve_doi_citation, cur["publishedIn"]
            )

        detected_kingdom = gbif_lookup_kingdom(cur["kingdom"]) if cur.get("kingdom") else None
        probable_year = _probable_year(cur.get("publishedIn"), detected_kingdom)
        if probable_year is not None:
            struct.links["gbif"]["probable_year"] = probable_year
        if not is_classification and detected_kingdom:
            # Kingdom signal detected with no extra call: "kingdom" is
            # already in the search response. See KingdomInconsistency.
            struct.links["gbif"]["detected_kingdom"] = detected_kingdom
        if not is_classification:
            # Same for family and order: flat fields of the search
            # response. See RankInconsistency. Not set when classifying,
            # where `struct.ranks` already covers them.
            if cur.get("family"):
                struct.links["gbif"]["detected_family"] = cur["family"]
            if cur.get("order"):
                struct.links["gbif"]["detected_order"] = cur["order"]

        # Vernacular names (`struct.vernacular`, namespaced by module)
        # must not depend on whether GBIF drives the classification, or
        # they vanish when another source wins.
        taxref_names: list[str] = []

        async def fetch_vernacular(offset: int) -> tuple[list[tuple[str | None, str]], int, bool]:
            page = await adapter.vernacular_names_page(key, offset)
            raw = page.get("results", [])
            taxref_names.extend(
                _html.unescape(c["vernacularName"])
                for c in raw
                if c.get("language") == "fra" and c.get("source") == "TAXREF"
            )
            names = [(c.get("language"), _html.unescape(c["vernacularName"])) for c in raw]
            return names, len(raw), page.get("endOfRecords", True)

        pairs, _ = await collect_pages(fetch_vernacular)
        vernacular = groupe_par_langue(pairs)
        if vernacular:
            struct.vernacular["GBIF"] = vernacular
        if taxref_names:
            # The MNHN/TAXREF reference ("INPN" source) is unreachable
            # directly: GBIF re-exposes the same names (source "TAXREF")
            # as a stopgap.
            struct.vernacular["INPN"] = {"fr": taxref_names}

        # Same workaround for the id: TAXREF is also published as a
        # separate GBIF checklist (`TAXREF_DATASET_KEY`). `related`
        # finds the TAXREF record of the same concept, whose `taxonID`
        # is the CD_NOM (INPN id), whether or not a French name exists.
        taxref_records = await adapter.taxref_related(key)
        cd_nom = next((r["taxonID"] for r in taxref_records if r.get("taxonID")), None)
        if cd_nom:
            struct.links["gbif"]["inpn_id"] = cd_nom

        accepted_key = cur.get("acceptedKey")
        is_synonym = accepted_key is not None and accepted_key != key
        # Nomenclatural status of this very record (see
        # RankInconsistency), set before the redirect: a redirected hop
        # rebuilds "gbif" for the accepted target, so no stale status
        # remains.
        struct.links["gbif"]["detected_status"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:

            async def resolve_accepted() -> str | None:
                assert accepted_key is not None  # guaranteed by is_synonym above
                accepted_info = await _taxon_info(adapter, accepted_key)
                return accepted_info["name"] if accepted_info is not None else None

            handled, result = await follow_synonym(
                struct,
                "gbif",
                is_classification,
                options,
                hop,
                resolve_accepted,
                lambda next_hop: self._collect(struct, is_classification, options, hop=next_hop),
            )
            if handled:
                return result
            # follow_synonyms is off: no early return, the
            # classification is built from this synonym rather than the
            # accepted taxon.

        if not is_classification:
            return struct

        struct.taxon.author = format_author(info["author"])
        struct.taxon.rank = gbif_to_wp_rank(cur["rank"])
        if "extinct" in info:
            struct.taxon.extinct = info["extinct"]
        # `info["name"]` (from `_taxon_info`, falling back on the raw
        # scientific name for names GBIF does not decompose, e.g.
        # viruses) rather than `cur["canonicalName"]`, absent for those.
        struct.taxon.name = info["name"].strip()
        struct.classification = "GBIF"
        struct.classification_taxobox = "GBIF"

        ranks: list[RankName] = []
        for marker in GBIF_WP:
            field = marker.lower()
            if field not in cur:
                continue
            value = cur[field]
            if marker == "KINGDOM":
                struct.kingdom = gbif_lookup_kingdom(value)
                continue
            buf = gbif_to_wp_rank(marker)
            if buf == struct.taxon.rank:
                continue
            entry: dict = {"name": value, "rank": buf}
            key_field = f"{field}Key"
            if key_field in cur:
                profiles = await adapter.species_profiles(cur[key_field])
                for p in profiles:
                    if "extinct" in p:
                        entry["extinct"] = p["extinct"]
                        break
            ranks.append(RankName.model_validate(entry))
        struct.ranks = ranks

        if not struct.kingdom:
            return None

        basionym_key = cur.get("basionymKey")
        if basionym_key:
            basionym_record = await adapter.species_record(basionym_key)
            if basionym_record and basionym_record.get("canonicalName"):
                struct.basionym = Basionym(
                    name=basionym_record["canonicalName"].strip(),
                    author=format_author((basionym_record.get("authorship") or "").strip()),
                    source="GBIF",
                )

        if cur.get("numDescendants", 0) > 0:

            async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
                page = await adapter.children_page(key, offset)
                raw = page.get("results", [])
                out = []
                for c in raw:
                    if c.get("rank") == "UNRANKED" or "canonicalName" not in c:
                        continue
                    child_info = await _taxon_info(adapter, c["key"])
                    if child_info is not None:
                        out.append(
                            RankName(
                                name=child_info["name"],
                                rank=child_info.get("rank"),
                                author=child_info.get("author"),
                                extinct=child_info.get("extinct"),
                            )
                        )
                return out, len(raw), page.get("endOfRecords", True)

            items, truncated = await collect_pages(
                fetch_children, limit=as_limit(options.list_limit)
            )
            if items:
                struct.subtaxa = SubTaxonList(items=items, source="GBIF", truncated=truncated)

        async def fetch_synonyms(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.synonyms_page(key, offset)
            raw = page.get("results", [])
            out = []
            for c in raw:
                blob = await _taxon_info(adapter, c["key"])
                if blob is not None:
                    out.append(
                        RankName(
                            name=blob["name"],
                            author=format_author(blob["author"]),
                            rank=blob.get("rank"),
                        )
                    )
            return out, len(raw), page.get("endOfRecords", True)

        synonyms, truncated = await collect_pages(
            fetch_synonyms, limit=as_limit(options.list_limit)
        )
        if synonyms:
            struct.synonyms = SynonymList(items=synonyms, source="GBIF", truncated=truncated)

        return struct

    def render_bioref(self, struct: Struct) -> list[str] | None:
        """Render {{GBIF}} and, if linked, {{CatalogueofLife}}."""
        data = struct.links.get("gbif")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        col_xr = data.get("col_xr")
        # When `data["id"]` is the ChecklistBank (COL XR) id it no
        # longer denotes the GBIF backbone but the COL XR record
        # (`col_xr`): {{GBIF}} must cite that record's name, author,
        # rank and extinction, or the citation contradicts the page the
        # id points to.
        source = col_xr if col_xr is not None else data
        rank = source.get("rank") or struct.taxon.rank
        target = wp_apply_italics(source["name"], rank, struct.kingdom)
        if author := source.get("author"):
            target += " " + author
        extinct_param = " | éteint=oui" if source.get("extinct") else ""
        # `synonym_flag` reflects the backbone status: only for the
        # legacy numeric key, never for an id substituted by COL XR
        # (`find_col_xr_link` never returns a synonym record).
        synonym_flag = " | nv" if data.get("synonym") and col_xr is None else ""
        out = [
            f"{{{{GBIF | {data['id']} | {target}{extinct_param}{synonym_flag} | consulté "
            f"le={cdate} }}}}"
        ]
        if col_xr is not None:
            # ChecklistBank (COL XR) id rather than the legacy numeric
            # key: the same record exists on catalogueoflife.org, hence
            # this second link, citing the same as {{GBIF}} so that
            # `compute_ext_link_items` sees one reference.
            out.append(
                f"{{{{CatalogueofLife | {data['id']} | {target}{extinct_param} | consulté "
                f"le={cdate} }}}}"
            )
        return out

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug links to GBIF and, if known, INPN."""
        data = struct.links.get("gbif")
        if not data or "id" not in data:
            return None
        path = "species" if isinstance(data["id"], int) else "taxon"
        link = simple_debug_link(struct, "gbif", f"https://www.gbif.org/{path}/{{id}}", "GBIF")
        if link and data.get("inpn_id"):
            # Same page as the `inpn` module would show for this id;
            # usable even when `inpn` itself fails (403 server-side), a
            # normal browser not being blocked.
            link += (
                f" <a href='https://taxref.mnhn.fr/taxref-web/taxa/{data['inpn_id']}' "
                f"target='_blank' rel='noopener noreferrer'>INPN</a>"
            )
        return link


register_module(GbifModule)
