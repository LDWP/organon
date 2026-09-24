"""Light resolution of the ChecklistBank id of an already resolved name.

COL XR is dataset 3LXR. Used by `organon.modules.gbif.module` for its
{{GBIF}} link (the template accepts these ids) and a second
{{CatalogueofLife}} link. Distinct from the full COL XR classification:
the two may differ, and this lookup is only a display id for the
classification GBIF already retained.

Makes no HTTP call itself; see adapter.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from organon.core.domains import kingdom_from_classification
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.common import format_author


@dataclass
class ColXrLinkInfo:
    """Name, author and rank as COL XR reports them for record `id`.

    Same fields as `ColModule` computes for `struct.links["col"]`, so
    the {{CatalogueofLife}} link built by `GbifModule` cites the same
    author as `ColModule` would; otherwise the two lines would differ
    and `compute_ext_link_items` would not merge them.
    """

    id: str
    nom: str
    auteur: str | None
    rang: str | None
    eteint: bool | None


def _kingdom_matches(r: dict, domain: str) -> bool:
    """Return True if the record fits the domain (any if unfiltered)."""
    if domain in ("*", ""):
        return True
    return kingdom_from_classification(r.get("classification", [])) == domain


def _rank_name(classification: list[dict], rank: str) -> str:
    """Return the name at `rank` in a classification, or ""."""
    return next((c.get("name", "") for c in classification if c.get("rank") == rank), "")


_EUKARYOTE_ONLY_CODES = {
    # ICNafp (botanical, also algae and fungi) and ICZN (zoological,
    # also many protists) apply to no prokaryote: a record of that code
    # on Bacteria or Archaea is an internal inconsistency, not a mere
    # classification disagreement.
    "botanical",
    "zoological",
}
_INCOMPATIBLE_KINGDOMS_BOTANICAL = {"Animalia"}
_INCOMPATIBLE_KINGDOMS_ZOOLOGICAL = {"Plantae", "Viridiplantae", "Fungi"}
_PROKARYOTE_DOMAINS = {"Bacteria", "Archaea"}


def _is_inconsistent_code(r: dict) -> bool:
    """Return True if the nomenclatural code contradicts the kingdom.

    `usage.name.code` (botanical, zoological, bacterial…) against the
    declared kingdom or domain is a reliable sign of a badly merged
    record in 3LXR, typically a Plazi treatment of an unrelated article
    absorbed as the "accepted" record of a homonym, not a real
    disagreement. Seen for Escherichia coli (NT3L7) and Toxoplasma
    gondii (VBKRN); VB8KH is caught by `_kingdom_matches` instead.
    """
    code = r["usage"]["name"].get("code")
    if code not in _EUKARYOTE_ONLY_CODES and code != "bacterial":
        return False
    classification = r.get("classification", [])
    kingdom = _rank_name(classification, "kingdom")
    domain = _rank_name(classification, "domain")
    if code == "botanical":
        return kingdom in _INCOMPATIBLE_KINGDOMS_BOTANICAL or domain in _PROKARYOTE_DOMAINS
    if code == "zoological":
        return kingdom in _INCOMPATIBLE_KINGDOMS_ZOOLOGICAL or domain in _PROKARYOTE_DOMAINS
    return domain == "Eukaryota"  # code == "bacterial" on a eukaryote


_SUBGENUS_RE = re.compile(r"\s*\([^)]*\)")
_LATIN_GENDER_ENDINGS = ("us", "a", "um")


def _strip_subgenus(name: str) -> str:
    """Remove the parenthesized subgenus ("Mus (Mus) musculus").

    Lets a binomial be compared with the trinomial notation
    ChecklistBank uses for some records, which `type=EXACT` does not
    match.
    """
    return _SUBGENUS_RE.sub("", name).strip()


_SUBGENUS_BEFORE_EPITHET_RE = re.compile(r"^(\S+) \([^)]*\) (?=\S)")


def strip_subgenus_before_epithet(name: str) -> str:
    """Remove a subgenus only when followed by an epithet.

    The name of a subgenus itself ("Mus (Mus)") is kept.
    """
    return _SUBGENUS_BEFORE_EPITHET_RE.sub(r"\1 ", name)


def _latin_gender_variants(name: str) -> list[str]:
    """Return Latin gender variants (-us/-a/-um) of the last word.

    To find a binomial whose epithet was corrected between sources that
    do not republish together (Macrovipera lebetina vs lebetinus). A
    last resort only (see `resolve_col_xr_matches`): not a general fuzzy
    search.
    """
    base, sep, last = name.rpartition(" ")
    if not sep:
        return []
    for ending in _LATIN_GENDER_ENDINGS:
        if last.endswith(ending):
            root = last[: -len(ending)]
            return [f"{base} {root}{other}" for other in _LATIN_GENDER_ENDINGS if other != ending]
    return []


async def _canonical_search(adapter: ColXrAdapter, name: str) -> list[dict]:
    """Search `name` without `type=EXACT` and keep the strict matches.

    Keep candidates whose scientific name, subgenus removed, equals
    `name` without subgenus: strict enough to ignore the noise of an
    unfiltered search, loose enough to find a record with a subgenus.
    """
    target = _strip_subgenus(name)
    results = await adapter.search(name, exact=False)
    return [r for r in results if _strip_subgenus(r["usage"]["name"]["scientificName"]) == target]


def _merge_unique(*groups: list[dict]) -> list[dict]:
    """Merge record lists, dropping duplicate ids."""
    seen: set[str] = set()
    merged: list[dict] = []
    for group in groups:
        for r in group:
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append(r)
    return merged


async def resolve_col_xr_matches(adapter: ColXrAdapter, name: str) -> list[dict]:
    """Resolve `name` in COL XR with progressive fallbacks.

    Shared by `ColModule` and the `find_col_xr_*` functions. Covers two
    form disagreements, which `type=EXACT` misses: the subgenus notation
    ("Mus (Mus) musculus" for the query "Mus musculus", even when only
    the form without subgenus exists as a literal synonym) and a Latin
    gender change of the epithet.

    Return the exact search merged with the candidates of the first
    fallback that succeeds (subgenus removed, then Latin gender
    variants). The exact search stays first, to keep a literal synonym
    whose redirect to the accepted name callers still use.
    """
    results = await adapter.search(name)
    exact = [r for r in results if r["usage"]["name"]["scientificName"] == name]
    if exact and any(r["usage"]["status"] == "accepted" for r in exact):
        return exact

    candidates = await _canonical_search(adapter, name)
    if candidates:
        return _merge_unique(exact, candidates)

    for variant in _latin_gender_variants(name):
        candidates = await _canonical_search(adapter, variant)
        if candidates:
            return _merge_unique(exact, candidates)

    return exact or results


def select_col_xr_candidate(candidates: list[dict], domain: str) -> dict | None:
    """Pick one ChecklistBank candidate among those filtered by status.

    Shared by `ColModule` and the `find_col_xr_*` functions.

    1. Restrict to the `domain` kingdom if known and at least one
       candidate matches.
    2. If several remain, prefer `usage.merged` false: true marks a
       record assembled automatically by the cross-checklist merge of
       3LXR (often a Plazi treatment) rather than natively curated.
    3. If still several, drop those whose nomenclatural code
       contradicts their kingdom or domain (`_is_inconsistent_code`).
    4. Otherwise keep ChecklistBank's order (first candidate) rather
       than refuse: such cases were rare.
    """
    if not candidates:
        return None
    matching = [r for r in candidates if _kingdom_matches(r, domain)] or candidates
    if len(matching) > 1:
        not_merged = [r for r in matching if not r["usage"].get("merged")]
        matching = not_merged or matching
    if len(matching) > 1:
        consistent = [r for r in matching if not _is_inconsistent_code(r)]
        matching = consistent or matching
    return matching[0]


def _to_link_info(cur: dict) -> ColXrLinkInfo:
    """Build a `ColXrLinkInfo` from a ChecklistBank record."""
    usage = cur["usage"]
    name = usage["name"]
    return ColXrLinkInfo(
        id=cur["id"],
        nom=name["scientificName"],
        auteur=format_author(name.get("authorship")),
        rang=col_xr_to_wp_rank(name["rank"]) if "rank" in name else None,
        eteint=usage.get("extinct"),
    )


async def find_col_xr_link(adapter: ColXrAdapter, name: str, domain: str) -> ColXrLinkInfo | None:
    """Return the link info of the accepted COL XR record of `name`.

    None if no accepted entry matches the name (and the kingdom, if
    `domain` is set): GBIF then keeps its numeric id. Synonyms are
    ignored, unlike `ColModule`: a reference link must point to the
    same accepted record GBIF resolved, never to another status.
    """
    candidates = await resolve_col_xr_matches(adapter, name)
    accepted = [r for r in candidates if r["usage"]["status"] == "accepted"]
    cur = select_col_xr_candidate(accepted, domain)
    return _to_link_info(cur) if cur is not None else None


async def resolve_col_xr_concept_id(adapter: ColXrAdapter, name: str, domain: str) -> str | None:
    """Return the id of the ACCEPTED concept denoted by `name`.

    `name` may be the accepted name itself or a synonym COL XR redirects
    to it (`usage.accepted.id`), unlike `find_col_xr_link`. Used by
    `subtaxa_merge.reconcile_synonym_groups` to recognize as one taxon
    two spellings that COL XR explicitly links, never by name
    similarity. None if `name` has no matching entry.
    """
    candidates = await resolve_col_xr_matches(adapter, name)

    accepted = [r for r in candidates if r["usage"]["status"] == "accepted"]
    cur = select_col_xr_candidate(accepted, domain)
    if cur is not None:
        return cur["id"]

    synonyms = [
        r for r in candidates if r["usage"]["status"] == "synonym" and r["usage"].get("accepted")
    ]
    cur = select_col_xr_candidate(synonyms, domain)
    return cur["usage"]["accepted"]["id"] if cur is not None else None
