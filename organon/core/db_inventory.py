"""Inventaire des bases de données biologiques considérées pour Organon — intégrées ou non.

Charge `organon/core/data/db_inventory.yaml` (transcription de l'inventaire de sondage tenu à
jour hors dépôt) et le fusionne avec `organon.core.registry` : pour toute source dont l'id
correspond à un module réellement enregistré, le statut affiché vient du registre (vérité
vivante) plutôt que du fichier de données, qui n'est qu'un instantané pouvant dater d'avant une
intégration récente (voir `tropicos` dans le YAML, marqué non intégré à sa rédaction mais
disponible en pratique aujourd'hui).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from organon.core.registry import all_modules, default_classification_module

DATA_DIR = Path(__file__).resolve().parent / "data"

AccesType = Literal[
    "api_rest",
    "soap",
    "scraping",
    "verification_http",
    "export",
    "contact_requis",
    "bloque",
    "mort",
    "inconnu",
]

Statut = Literal[
    "disponible",
    "non_sonde",
    "bloque",
    "bloque_temporaire",
    "mort",
    "contact_requis",
    "ecarte",
    "hors_perimetre",
    "retire",
]
"""`ecarte` désigne une base jamais intégrée (candidate rejetée avant tout portage) ; `retire`
désigne une base qui a été intégrée puis débranchée après coup pour un motif éditorial (le module
existait et fonctionnait, mais son maintien ne convenait plus) — ne pas confondre les deux, le
second implique un travail d'intégration déjà fait et volontairement retiré."""


class ClassificationInfo(BaseModel):
    """`estime=True` signifie que la capacité de classification n'a jamais été vérifiée dans du
    code (ni ce dépôt ni l'ancien PHP) : une supposition sur la nature de la base, à confirmer
    si elle est portée un jour. `detail` porte la justification associée (ex. « côté PHP »,
    « défaut », rangs couverts)."""

    possible: bool
    estime: bool = False
    detail: str | None = None


class AccesInfo(BaseModel):
    type: AccesType
    detail: str


class SourceEntry(BaseModel):
    """Une base de données, intégrée ou non. `elements_recoltes` ne prend sens que pour une
    source `disponible` (rien n'est collecté pour une base non intégrée)."""

    id: str
    nom: str
    url: str | None = None
    statut: Statut
    classification: ClassificationInfo
    elements_recoltes: list[str] = []
    acces: AccesInfo
    derniere_maj: str | None = None
    notes: str | None = None
    is_default: bool = False


class SourceCategory(BaseModel):
    id: str
    nom: str
    sources: list[SourceEntry]


class DbInventory(BaseModel):
    derniere_maj: str
    categories: list[SourceCategory]


@lru_cache(maxsize=1)
def load_db_inventory(path: Path | None = None) -> DbInventory:
    target = path or (DATA_DIR / "db_inventory.yaml")
    with target.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return DbInventory.model_validate(raw)


def build_sources_overview(inventory: DbInventory | None = None) -> DbInventory:
    """Vue fusionnée pour GET /api/v1/sources : le fichier de données statique complété par
    l'état réel du registre de modules. Suppose que `ensure_modules_registered()` a déjà été
    appelé par l'appelant (comme pour `organon.api.routes.modules`).

    `inventory` est surtout là pour les tests (fusion contre un inventaire synthétique plutôt
    que contre le fichier YAML réel) ; le paramètre par défaut (`None`) recharge celui-ci."""
    inventory = inventory or load_db_inventory()
    live = all_modules()
    default_id = default_classification_module()
    seen: set[str] = set()

    categories = []
    for category in inventory.categories:
        sources = [_reconcile(entry, live.get(entry.id), default_id) for entry in category.sources]
        seen.update(entry.id for entry in category.sources)
        categories.append(category.model_copy(update={"sources": sources}))

    # Modules enregistrés après la dernière mise à jour du fichier de données : ajoutés dans une
    # catégorie de repli plutôt que rendus invisibles sur la page.
    extra = [module for module_id, module in live.items() if module_id not in seen]
    if extra:
        categories.append(
            SourceCategory(
                id="autres_modules_actifs",
                nom="Autres modules actifs (non encore répertoriés)",
                sources=[_from_live_only(module, default_id) for module in extra],
            )
        )

    return DbInventory(derniere_maj=inventory.derniere_maj, categories=categories)


def _reconcile(entry: SourceEntry, module, default_id: str | None) -> SourceEntry:
    if module is None:
        return entry
    return entry.model_copy(
        update={
            "statut": "disponible",
            "classification": ClassificationInfo(
                possible=module.meta.can_classify,
                estime=False,
                detail=entry.classification.detail,
            ),
            "is_default": module.meta.id == default_id,
        }
    )


def _from_live_only(module, default_id: str | None) -> SourceEntry:
    domains = module.meta.domains if isinstance(module.meta.domains, str) else ", ".join(module.meta.domains)
    return SourceEntry(
        id=module.meta.id,
        nom=module.meta.id.upper(),
        statut="disponible",
        classification=ClassificationInfo(possible=module.meta.can_classify, estime=False),
        acces=AccesInfo(type="inconnu", detail=f"Domaines : {domains}"),
        is_default=module.meta.id == default_id,
    )
