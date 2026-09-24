"""Access to the ICTV data: the embedded dataset, with no network call.

The data is `organon/core/data/ictv_taxonomy.tsv` (see
scripts/build_ictv_taxonomy.py). ICTV has no API queryable by taxon name
(its Taxonomy Browser only searches by RANK name, and the EBI/OLS
ontology is obsolete since 2009), so the only up-to-date data is the VMR
export published on GitHub, embedded here rather than queried.

Exact case-insensitive search only, as the source data has no fuzzy
search or synonyms.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from operator import itemgetter
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "core" / "data" / "ictv_taxonomy.tsv"

# Lineage columns of the dataset, broadest to most specific (see
# scripts/build_ictv_taxonomy.py for the columns kept or dropped).
LINEAGE_COLUMNS = [
    "Realm",
    "Subrealm",
    "Kingdom",
    "Phylum",
    "Subphylum",
    "Class",
    "Subclass",
    "Order",
    "Suborder",
    "Family",
    "Subfamily",
    "Genus",
    "Subgenus",
    "Species",
]


@dataclass(frozen=True)
class IctvRecord:
    """An ICTV taxon, at any rank of `LINEAGE_COLUMNS`.

    `ancestors` goes from the broadest to the taxon itself (last item)
    and keeps only the filled ranks: the ICTV lineage is sparse.
    """

    ancestors: tuple[tuple[str, str], ...]
    ictv_id: str | None

    @property
    def rang_colonne(self) -> str:
        """Return the lineage column (rank) of the taxon."""
        return self.ancestors[-1][0]

    @property
    def nom(self) -> str:
        """Return the name of the taxon."""
        return self.ancestors[-1][1]


def _load_rows(path: Path) -> list[dict[str, str]]:
    """Read the TSV rows."""
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


@lru_cache(maxsize=4)
def _build_index(
    path: Path,
) -> tuple[dict[str, IctvRecord], dict[str, frozenset[tuple[str, str]]]]:
    """Build the name index and the immediate-children table.

    Name (lowercase) to `IctvRecord`, and parent name (lowercase) to its
    set of (column, name) children, in a single pass. A family may have
    genera attached directly and others through a subfamily, so the
    sparse lineage is handled row by row, not by a fixed column shift.
    """
    rows = _load_rows(path)
    index: dict[str, IctvRecord] = {}
    children: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for row in rows:
        chain = [(col, row[col]) for col in LINEAGE_COLUMNS if row.get(col)]
        for i, (col, name) in enumerate(chain):
            key = name.lower()
            if key not in index:
                # A homonym across two lineages would silently resolve
                # to the first TSV occurrence. Absent from the current
                # VMR (22670 names, each with a single ancestor
                # lineage); to watch if a future export has one.
                ictv_id = row.get("ICTV_ID") or None if col == "Species" else None
                index[key] = IctvRecord(ancestors=tuple(chain[: i + 1]), ictv_id=ictv_id)
            if i > 0:
                children[chain[i - 1][1].lower()].add((col, name))

    return index, {k: frozenset(v) for k, v in children.items()}


class IctvAdapter:
    """Reader of the embedded ICTV dataset."""

    def __init__(self, path: Path = DATA_PATH) -> None:
        """Use the given dataset path."""
        self._path = path

    def find(self, name: str) -> IctvRecord | None:
        """Return the record of a name (case-insensitive), or None."""
        index, _ = _build_index(self._path)
        return index.get(name.lower())

    def children_of(self, name: str) -> list[tuple[str, str]]:
        """Return the immediate children of `name` as (column, name)."""
        _, children = _build_index(self._path)
        return sorted(children.get(name.lower(), frozenset()), key=itemgetter(1))
