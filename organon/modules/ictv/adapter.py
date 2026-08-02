"""Couche d'accès aux données ICTV : lecture du dataset embarqué
(organon/core/data/ictv_taxonomy.tsv, voir scripts/build_ictv_taxonomy.py), aucun appel réseau.
L'ICTV n'expose aucune API interrogeable par nom de taxon (Taxonomy Browser limité à la recherche
par nom de RANG, ontologie ICTV hébergée par l'EBI/OLS obsolète depuis 2009 — vérifié) : la seule
donnée à jour est le VMR export publié sur GitHub, embarqué ici comme organon/core/data/ranks.yaml
plutôt qu'interrogé en direct.

Recherche exacte insensible à la casse uniquement (comme le permet la donnée source, qui n'offre
aucune notion de recherche floue ni de synonymes)."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "core" / "data" / "ictv_taxonomy.tsv"

LINEAGE_COLUMNS = [
    "Realm", "Subrealm", "Kingdom", "Phylum", "Subphylum", "Class", "Subclass",
    "Order", "Suborder", "Family", "Subfamily", "Genus", "Subgenus", "Species",
]
"""Colonnes de lignée du dataset, du plus large au plus spécifique (voir
scripts/build_ictv_taxonomy.py pour le détail des colonnes retenues/écartées)."""


@dataclass(frozen=True)
class IctvRecord:
    """Un taxon ICTV, à n'importe quel rang de `LINEAGE_COLUMNS`. `ancestors` va du plus large
    au taxon lui-même inclus (dernier élément), ne contient que les rangs renseignés (la lignée
    ICTV est creuse : beaucoup de taxons n'ont pas de valeur à tous les rangs intermédiaires)."""

    ancestors: tuple[tuple[str, str], ...]
    ictv_id: str | None

    @property
    def rang_colonne(self) -> str:
        return self.ancestors[-1][0]

    @property
    def nom(self) -> str:
        return self.ancestors[-1][1]


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


@lru_cache(maxsize=4)
def _build_index(path: Path) -> tuple[dict[str, IctvRecord], dict[str, frozenset[tuple[str, str]]]]:
    """Construit l'index nom (minuscule) -> IctvRecord, et la table des enfants immédiats
    (nom de parent en minuscule -> ensemble de (colonne, nom) enfants), en un seul passage sur le
    dataset. Un taxon peut apparaître comme parent de rangs enfants différents selon les lignes
    (ex. une famille dont certains genres sont directement rattachés et d'autres passent par une
    sous-famille) : la lignée creuse est donc gérée ligne par ligne plutôt que par décalage de
    colonne fixe."""
    rows = _load_rows(path)
    index: dict[str, IctvRecord] = {}
    children: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for row in rows:
        chain = [(col, row[col]) for col in LINEAGE_COLUMNS if row.get(col)]
        for i, (col, nom) in enumerate(chain):
            key = nom.lower()
            if key not in index:
                ictv_id = row.get("ICTV_ID") or None if col == "Species" else None
                index[key] = IctvRecord(ancestors=tuple(chain[: i + 1]), ictv_id=ictv_id)
            if i > 0:
                children[chain[i - 1][1].lower()].add((col, nom))

    return index, {k: frozenset(v) for k, v in children.items()}


class IctvAdapter:
    def __init__(self, path: Path = DATA_PATH) -> None:
        self._path = path

    def find(self, name: str) -> IctvRecord | None:
        index, _ = _build_index(self._path)
        return index.get(name.lower())

    def children_of(self, name: str) -> list[tuple[str, str]]:
        """Enfants immédiats de `name` (colonne, nom), triés par nom."""
        _, children = _build_index(self._path)
        return sorted(children.get(name.lower(), frozenset()), key=lambda item: item[1])
