"""Detect inconsistencies between classification and enrichment.

A name may denote unrelated homonyms depending on the source (e.g.
"Morus", mulberry vs gannet). A differing kingdom, family, order or
status is a possible sign of it. Pure derivation from a resolved
`Struct`, with no third-party call.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from organon.core.domains import build_module_domain_tree, domain_covers
from organon.core.models import KingdomInconsistency, RankInconsistency, Struct
from organon.core.registry import get_module

# Implicit status of the winning taxon: a synonym is re-resolved to
# its accepted target, unless `follow_synonyms` is off and the module
# reports its own `detected_status`, which then wins.
_DEFAULT_SELECTED_STATUS = "accepté"

# Compared rank -> key in `struct.links[<module>]` holding it.
_DETECTED_RANK_KEYS: dict[str, Literal["detected_family", "detected_order"]] = {
    "famille": "detected_family",
    "ordre": "detected_order",
}

# Sentinel for a kingdom label unknown to every chart: not a real
# signal, excluded to avoid false positives.
_UNKNOWN_KINGDOM = "neutre"

# Same bounds as `authors._YEAR_RE` (1300-2099), as a free search.
_YEAR_TOKEN_RE = re.compile(r"\b(1[3-9]\d\d|20\d\d)\b")


def gbif_probable_year_validated(struct: Struct, selected_author: str | None) -> int | None:
    """Confirm GBIF's probable year against another module.

    GBIF has no structured year; it is regex-extracted from free text.
    Return it only if another module reports it in its own author.
    Return None if `selected_author` already carries a year.
    """
    if selected_author and _YEAR_TOKEN_RE.search(selected_author):
        return None
    year = struct.links.get("gbif", {}).get("probable_year")
    if year is None:
        return None
    target = str(year)
    for module_id, data in struct.links.items():
        if module_id == "gbif" or not isinstance(data, dict):
            continue
        if target in _YEAR_TOKEN_RE.findall(data.get("author") or ""):
            return year
    return None


def detect_kingdom_inconsistencies(
    struct: Struct, classification_id: str
) -> list[KingdomInconsistency]:
    """Return modules whose `detected_kingdom` differs from the struct.

    Partial: only modules exposing it without an extra network call
    (GBIF, ITIS, WoRMS) can trigger.
    """
    inconsistencies: list[KingdomInconsistency] = []
    for module_id, data in struct.links.items():
        if module_id == classification_id or not isinstance(data, dict):
            continue
        detected_kingdom = data.get("detected_kingdom")
        if (
            detected_kingdom
            and detected_kingdom != _UNKNOWN_KINGDOM
            and detected_kingdom != struct.kingdom
        ):
            inconsistencies.append(
                KingdomInconsistency(
                    module=module_id,
                    suggested_kingdom=detected_kingdom,
                    retained_kingdom=struct.kingdom,
                )
            )
    return inconsistencies


def detect_rank_inconsistencies(struct: Struct, classification_id: str) -> list[RankInconsistency]:
    """Return modules disagreeing on family, order or status.

    A real disagreement: both sources have a value. A source silent on
    a rank never appears. Partial: only GBIF and CoL XR expose them
    without an extra network call.
    """
    inconsistencies: list[RankInconsistency] = []
    selected_values = {r.rank: r.name for r in struct.ranks if r.rank in _DETECTED_RANK_KEYS}
    classification_data = struct.links.get(classification_id) or {}
    selected_status = classification_data.get("detected_status") or _DEFAULT_SELECTED_STATUS

    for module_id, data in struct.links.items():
        if module_id == classification_id or not isinstance(data, dict):
            continue
        for rank, key in _DETECTED_RANK_KEYS.items():
            selected_value = selected_values.get(rank)
            suggested_value = data.get(key)
            if selected_value and suggested_value and suggested_value != selected_value:
                inconsistencies.append(
                    RankInconsistency(
                        module=module_id,
                        compared_field=rank,
                        suggested_value=suggested_value,
                        retained_value=selected_value,
                    )
                )
        suggested_status = data.get("detected_status")
        if suggested_status and suggested_status != selected_status:
            inconsistencies.append(
                RankInconsistency(
                    module=module_id,
                    compared_field="statut",
                    suggested_value=suggested_status,
                    retained_value=selected_status,
                )
            )
    return inconsistencies


def consistent_kingdom_classifications(
    successes: list[str], kingdoms: dict[str, str]
) -> tuple[list[str], list[str], str | None]:
    """Split classification successes by kingdom majority.

    Return (coherent, excluded, majority kingdom). A cross-kingdom
    homonym must not win on specialization or priority alone. Only a
    strict majority of the known kingdoms excludes outliers; empty or
    "neutre" kingdoms carry no signal and are always kept.
    """
    flagged = {
        cid: kingdoms[cid]
        for cid in successes
        if kingdoms.get(cid) and kingdoms[cid] != _UNKNOWN_KINGDOM
    }
    if len(flagged) < 2:
        return successes, [], None

    majority_kingdom, majority_count = Counter(flagged.values()).most_common(1)[0]
    if majority_count * 2 <= len(flagged):
        return successes, [], None

    excluded = [cid for cid in successes if flagged.get(cid, majority_kingdom) != majority_kingdom]
    consistent = [cid for cid in successes if cid not in excluded]
    return consistent, excluded, majority_kingdom


def reference_module_is_consistent(module_id: str, kingdom: str) -> bool:
    """Return True if a reference module fits the taxon's kingdom.

    Based on `ModuleMeta.domains`. A finer declared domain than
    `struct.regne` (MDD, "mammifère") stays coherent. An empty or
    "neutre" kingdom is coherent by default.
    """
    if not kingdom or kingdom == _UNKNOWN_KINGDOM:
        return True
    module = get_module(module_id)
    if module is None:
        return True
    return domain_covers(kingdom, build_module_domain_tree(module.meta.domains))
