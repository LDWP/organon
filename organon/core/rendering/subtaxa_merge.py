"""Merge sub-taxa reported by several classification sources.

Species are matched across sources by EXACT name only: no fuzzy
matching, which would hide false positives. Sources reporting the
exact same species set form one group; any divergence forms its own
group with its COMPLETE list. Groups are ordered by decreasing size,
then by source order. The first is "primary" (checked, names the
taxon), the others "alternative" (unchecked, use the pronoun).

`reconcile_synonym_groups` is an optional async second phase for
groups of equal size that differ by synonymy.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from organon.core.models import RankName
from organon.core.rendering.grammar import (
    load_rank_table,
    wp_apply_italics,
    wp_definite_rank,
    wp_rank_name,
)
from organon.core.rendering.sections import (
    compute_rank_names,
    compute_rank_text,
    join_and,
    render_subtaxon_line,
)
from organon.core.rendering.support import retrieval_dates

__all__ = [
    "GroupKind",
    "MergedGroup",
    "MergedSpecies",
    "MergedSubtaxa",
    "merge_subtaxa",
    "reconcile_synonym_groups",
]

GroupKind = Literal["primary", "alternative"]


@dataclass
class MergedSpecies:
    """One species of a group."""

    name: str
    # Technical rank key (e.g. "sous-espèce"), letting the frontend
    # recompute `MergedSubtaxa.rank_text` as boxes are checked.
    rank: str
    # Ready-made wikitext line, see `sections.render_subtaxon_line`.
    line: str
    default_checked: bool


@dataclass
class MergedGroup:
    """Sources agreeing on one exact species set."""

    # Sources reporting exactly this species set, in `sources` order.
    sources: list[str]
    # "primary": largest group, checked by default, anchors the intro
    # sentence. "alternative": complete but divergent list, unchecked.
    kind: GroupKind
    # "Selon {{Bioref}} et …" or "Pour {{Bioref}}" clause. Excludes the
    # species count and rank, which the frontend recomputes.
    intro: str
    species: list[MergedSpecies]


@dataclass
class MergedSubtaxa:
    """Merged sub-taxa, ready for the frontend."""

    rank_text: str
    # Singular of `rank_text`, for groups with one species.
    rank_text_singular: str
    # Pronoun agreeing with the taxon rank, for later groups.
    pronoun: Literal["il", "elle"]
    # Explicit subject ("le genre ''Panthera''") for the first group
    # only; later groups use `pronoun`.
    taxon_phrase: str
    # Rank name (plural, singular) per rank key over all species, so
    # the frontend can recompute the rank text as boxes are checked.
    rank_names: dict[str, tuple[str, str]]
    groups: list[MergedGroup]


def _pronoun(taxon_rank: str) -> Literal["il", "elle"]:
    """Return the pronoun agreeing with the rank."""
    table = load_rank_table()
    if taxon_rank not in table.ranks:
        return "il"
    return "il" if table.ranks[taxon_rank].gender == "masculine" else "elle"


def _taxon_phrase(taxon_rank: str, taxon_name: str, kingdom: str) -> str:
    """Return the explicit subject, e.g. "le genre X"."""
    article = wp_definite_rank(taxon_rank)
    rank_name = wp_rank_name(taxon_rank, link=False, capitalize=False, plural=False)
    target = wp_apply_italics(taxon_name, taxon_rank, kingdom)
    if article is None or rank_name is None:
        return target
    return f"{article}{rank_name} {target}"


def _intro(sources_list: list[str], cdate: str) -> str:
    """Return the "Selon …" or "Pour …" citation clause."""
    citations = [f"{{{{Bioref|{s}|{cdate}}}}}" for s in sources_list]
    if len(citations) == 1:
        return f"Pour {citations[0]}"
    return "Selon " + join_and(citations)


def merge_subtaxa(
    taxon_rank: str, taxon_name: str, kingdom: str, sources: list[tuple[str, list[RankName]]]
) -> MergedSubtaxa:
    """Group `sources` by identical species set; render each group."""
    source_order: list[str] = []
    source_list: dict[str, list[RankName]] = {}
    name_to_species: dict[str, RankName] = {}

    for module_id, items in sources:
        if module_id in source_list:
            continue
        source_order.append(module_id)
        source_list[module_id] = items
        for sp in items:
            if sp.name not in name_to_species:
                name_to_species[sp.name] = sp

    all_species = [name_to_species[n] for n in name_to_species]
    rank_text, rank_text_singular, default_rank = compute_rank_text(all_species)
    rank_names = compute_rank_names(all_species)

    # Group sources reporting exactly the same species set (by name).
    group_order: list[frozenset[str]] = []
    group_sources: dict[frozenset[str], list[str]] = {}
    for module_id in source_order:
        key = frozenset(sp.name for sp in source_list[module_id])
        if key not in group_sources:
            group_sources[key] = []
            group_order.append(key)
        group_sources[key].append(module_id)

    # Largest group first; ties by first source order.
    group_order.sort(key=lambda k: (-len(k), source_order.index(group_sources[k][0])))

    cdate = retrieval_dates()
    groups = []
    for i, key in enumerate(group_order):
        ordered_sources = group_sources[key]
        kind: GroupKind = "primary" if i == 0 else "alternative"
        # Full list of the first source; the whole group agrees on it.
        species_names = sorted(sp.name for sp in source_list[ordered_sources[0]])
        groups.append(
            MergedGroup(
                sources=ordered_sources,
                kind=kind,
                intro=_intro(ordered_sources, cdate),
                species=[
                    MergedSpecies(
                        name=name,
                        rank=name_to_species[name].rank or default_rank,
                        line=render_subtaxon_line(
                            name_to_species[name], kingdom, default_rank, taxon_rank
                        ),
                        default_checked=(kind == "primary"),
                    )
                    for name in species_names
                ],
            )
        )

    return MergedSubtaxa(
        rank_text=rank_text,
        rank_text_singular=rank_text_singular,
        pronoun=_pronoun(taxon_rank),
        taxon_phrase=_taxon_phrase(taxon_rank, taxon_name, kingdom),
        rank_names=rank_names,
        groups=groups,
    )


def _merge_pair(
    primary: MergedGroup, secondary: MergedGroup, source_order: list[str], pairing: dict[str, str]
) -> MergedGroup:
    """Merge two equal-size groups whose orphan names were paired.

    `pairing` maps names of `primary` to those of `secondary`, a
    bijection already checked by the caller. `kind` and `intro` are
    provisional; the caller recomputes them.
    """
    primary_by_name = {s.name: s for s in primary.species}
    secondary_by_name = {s.name: s for s in secondary.species}
    species = [s for name, s in primary_by_name.items() if name in secondary_by_name]
    species += [primary_by_name[name] for name in pairing]
    return MergedGroup(
        sources=sorted(primary.sources + secondary.sources, key=source_order.index),
        kind="alternative",
        intro="",
        species=sorted(species, key=lambda s: s.name),
    )


def _resolved_ids(names: set[str], ids: list[str | None]) -> dict[str, str] | None:
    """Map names to resolved ids, or None if any is unresolved."""
    result: dict[str, str] = {}
    for name, cid in zip(names, ids, strict=True):
        if cid is None:
            return None
        result[name] = cid
    return result


async def reconcile_synonym_groups(
    groups: list[MergedGroup],
    source_order: list[str],
    resolve: Callable[[str], Awaitable[str | None]],
) -> list[MergedGroup]:
    """Merge groups of equal size that differ only by synonymy.

    `resolve(nom)` returns a stable external id (e.g. COL XR) or None;
    injected to keep this module free of network code. Merge only if
    each orphan name has exactly one counterpart with the same id (a
    complete bijection, no None), never on name similarity alone.
    """
    if len(groups) < 2:
        return list(groups)

    working = list(groups)
    cache: dict[str, str | None] = {}

    async def resolved(name: str) -> str | None:
        if name not in cache:
            cache[name] = await resolve(name)
        return cache[name]

    merged_once = True
    while merged_once:
        merged_once = False
        for i in range(len(working)):
            for j in range(i + 1, len(working)):
                ga, gb = working[i], working[j]
                if len(ga.species) != len(gb.species) or not ga.species:
                    continue
                a_first = source_order.index(ga.sources[0])
                b_first = source_order.index(gb.sources[0])
                primary, secondary = (ga, gb) if a_first <= b_first else (gb, ga)

                primary_names = {s.name for s in primary.species}
                secondary_names = {s.name for s in secondary.species}
                only_primary = primary_names - secondary_names
                only_secondary = secondary_names - primary_names
                if not only_primary:
                    continue  # groupes déjà identiques : ne devrait pas arriver (garde-fou)

                ids_primary, ids_secondary = await asyncio.gather(
                    asyncio.gather(*(resolved(n) for n in only_primary)),
                    asyncio.gather(*(resolved(n) for n in only_secondary)),
                )
                id_of_primary = _resolved_ids(only_primary, ids_primary)
                id_of_secondary = _resolved_ids(only_secondary, ids_secondary)
                if id_of_primary is None or id_of_secondary is None:
                    continue

                name_of_id_secondary: dict[str, str] = {}
                ambiguous = False
                for name, cid in id_of_secondary.items():
                    if cid in name_of_id_secondary:
                        ambiguous = True
                        break
                    name_of_id_secondary[cid] = name
                if ambiguous or any(
                    cid not in name_of_id_secondary for cid in id_of_primary.values()
                ):
                    continue

                pairing = {name: name_of_id_secondary[cid] for name, cid in id_of_primary.items()}
                if len(set(pairing.values())) != len(pairing):
                    continue  # bijection stricte : pas deux orphelins vers le même homologue

                working[i] = _merge_pair(primary, secondary, source_order, pairing)
                del working[j]
                merged_once = True
                break
            if merged_once:
                break

    cdate = retrieval_dates()
    working.sort(key=lambda g: (-len(g.species), source_order.index(g.sources[0])))
    return [
        MergedGroup(
            sources=g.sources,
            kind="primary" if i == 0 else "alternative",
            intro=_intro(g.sources, cdate),
            species=[
                MergedSpecies(name=s.name, rank=s.rank, line=s.line, default_checked=(i == 0))
                for s in g.species
            ],
        )
        for i, g in enumerate(working)
    ]
