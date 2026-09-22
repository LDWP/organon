"""Registry of third-party taxonomic database modules.

Modules register through `@register_module` on explicit import,
not directory scanning, so duplicates fail immediately.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from organon.core.config import GenerateOptions
from organon.core.domains import DomainSpec, DomainTree, build_module_domain_tree
from organon.core.models import Struct


@dataclass(frozen=True)
class ModuleMeta:
    """Declarative metadata of a module.

    `priority` breaks ties between competing classification modules.
    """

    id: str
    can_classify: bool
    can_render_external_link: bool
    domains: DomainSpec
    priority: int = 0
    is_default_classification: bool = False


class TaxonomyModule(ABC):
    """Adapter for one third-party taxonomic database.

    Network access and parsing live in `organon.modules.<id>.adapter`;
    this class only carries the orchestration.
    """

    meta: ClassVar[ModuleMeta]

    def is_configured(self) -> bool:
        """Return True if the module has what it needs to run.

        Override when a missing account or key makes the module fail
        entirely instead of being skipped.
        """
        return True

    @abstractmethod
    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect this module's data for `struct.taxon`.

        Return the updated struct (possibly a new object, e.g. after
        following a synonym), or None on failure.
        """
        raise NotImplementedError

    def render_bioref(self, struct: Struct) -> str | list[str] | None:
        """Render this module's {{Bioref}} entry.

        None means the module contributes no entry.
        """
        return None

    def debug_link(self, struct: Struct) -> str | None:
        """Return the raw link shown in the debug panel."""
        return None


_REGISTRY: dict[str, TaxonomyModule] = {}


def register_module(cls: type[TaxonomyModule]) -> type[TaxonomyModule]:
    """Register a `TaxonomyModule` subclass that defines `meta`."""
    if not hasattr(cls, "meta"):
        raise TypeError(f"{cls.__name__} doit définir un attribut de classe 'meta' (ModuleMeta)")
    instance = cls()
    if instance.meta.id in _REGISTRY:
        raise ValueError(f"module '{instance.meta.id}' déjà enregistré")
    _REGISTRY[instance.meta.id] = instance
    return cls


def all_modules() -> dict[str, TaxonomyModule]:
    """Return a copy of the registry."""
    return dict(_REGISTRY)


def get_module(module_id: str) -> TaxonomyModule | None:
    """Return the module registered under `module_id`, if any."""
    return _REGISTRY.get(module_id)


def classification_modules() -> list[str]:
    """Return the ids of modules usable for classification."""
    return [m.meta.id for m in _REGISTRY.values() if m.meta.can_classify]


def default_classification_module() -> str | None:
    """Return the default classification module id, if any."""
    for m in _REGISTRY.values():
        if m.meta.is_default_classification:
            return m.meta.id
    return None


def module_domain_trees(exclude: set[str] | None = None) -> dict[str, DomainTree]:
    """Build each registered module's domain tree.

    Meant for `organon.core.domains.possible_modules`. `exclude`
    omits disabled modules.
    """
    exclude = exclude or set()
    return {
        m.meta.id: build_module_domain_tree(m.meta.domains)
        for m in _REGISTRY.values()
        if m.meta.id not in exclude
    }


def module_priorities(exclude: set[str] | None = None) -> dict[str, int]:
    """Return module id -> priority, minus `exclude`."""
    exclude = exclude or set()
    return {m.meta.id: m.meta.priority for m in _REGISTRY.values() if m.meta.id not in exclude}
