"""Inventory of the biological databases considered for Organon.

Loads `data/db_inventory.yaml` and merges it with the registry. For
a registered module the registry status wins over the file, which
is only a snapshot.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from organon.core.registry import (
    TaxonomyModule,
    all_modules,
    default_classification_module,
)

DATA_DIR = Path(__file__).resolve().parent / "data"

AccessType = Literal[
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

# `ecarte`: never integrated. `retire`: integrated then removed.
# `en_attente`: registered but unconfigured (account or key missing);
# recomputed as `disponible` once configured.
Status = Literal[
    "disponible",
    "non_sonde",
    "bloque",
    "bloque_temporaire",
    "mort",
    "contact_requis",
    "ecarte",
    "hors_perimetre",
    "retire",
    "en_attente",
]


class ClassificationInfo(BaseModel):
    """Classification capability of a source.

    `estimated=True` means it was never verified in code, only guessed.
    `detail` carries the justification.
    """

    can_classify: bool
    estimated: bool = False
    detail: str | None = None


class AccessInfo(BaseModel):
    """How a source is accessed."""

    type: AccessType
    detail: str


class SourceFacet(BaseModel):
    """One site covered by a module, shown as its own row.

    E.g. `externe` covers Wikidata, Commons and Wikispecies.
    """

    name: str
    url: str | None = None
    harvested_items: list[str] = []


class SourceEntry(BaseModel):
    """A database, integrated or not.

    `harvested_items` only matters for an available source. With
    non-empty `facets`, per-site details live there instead.
    """

    id: str
    name: str
    url: str | None = None
    status: Status
    classification: ClassificationInfo
    harvested_items: list[str] = []
    facets: list[SourceFacet] = []
    access: AccessInfo
    last_updated: str | None = None
    notes: str | None = None
    is_default: bool = False


class SourceCategory(BaseModel):
    """A named group of sources."""

    id: str
    name: str
    sources: list[SourceEntry]


class DbInventory(BaseModel):
    """The full inventory of sources."""

    last_updated: str
    categories: list[SourceCategory]


@lru_cache(maxsize=1)
def load_db_inventory(path: Path | None = None) -> DbInventory:
    """Load the inventory from `path` or the bundled YAML."""
    target = path or (DATA_DIR / "db_inventory.yaml")
    with target.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return DbInventory.model_validate(raw)


def build_sources_overview(inventory: DbInventory | None = None) -> DbInventory:
    """Merge the static inventory with the live module registry.

    Assumes `ensure_modules_registered()` was already called.
    `inventory` defaults to the bundled file; tests pass their own.
    """
    inventory = inventory or load_db_inventory()
    live = all_modules()
    default_id = default_classification_module()
    seen: set[str] = set()

    categories = []
    for category in inventory.categories:
        sources = [_reconcile(entry, live.get(entry.id), default_id) for entry in category.sources]
        seen.update(entry.id for entry in category.sources)
        categories.append(category.model_copy(update={"sources": sources}))

    # Modules registered after the data file was last updated go in a
    # fallback category instead of being hidden.
    extra = [module for module_id, module in live.items() if module_id not in seen]
    if extra:
        categories.append(
            SourceCategory(
                id="autres_modules_actifs",
                name="Autres modules actifs (non encore répertoriés)",
                sources=[_from_live_only(module, default_id) for module in extra],
            )
        )

    return DbInventory(last_updated=inventory.last_updated, categories=categories)


def _reconcile(
    entry: SourceEntry, module: TaxonomyModule | None, default_id: str | None
) -> SourceEntry:
    if module is None:
        return entry
    status = "disponible" if module.is_configured() else "en_attente"
    return entry.model_copy(
        update={
            "status": status,
            "classification": ClassificationInfo(
                can_classify=module.meta.can_classify,
                estimated=False,
                detail=entry.classification.detail,
            ),
            "is_default": module.meta.id == default_id,
        }
    )


def _from_live_only(module: TaxonomyModule, default_id: str | None) -> SourceEntry:
    domains = (
        module.meta.domains
        if isinstance(module.meta.domains, str)
        else ", ".join(module.meta.domains)
    )
    return SourceEntry(
        id=module.meta.id,
        name=module.meta.id.upper(),
        status="disponible",
        classification=ClassificationInfo(can_classify=module.meta.can_classify, estimated=False),
        access=AccessInfo(type="inconnu", detail=f"Domaines : {domains}"),
        is_default=module.meta.id == default_id,
    )
