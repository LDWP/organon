"""Registre des modules d'accès aux bases taxonomiques tierces.

L'enregistrement se fait par import explicite (chaque module s'enregistre via le décorateur
`@register_module` quand son fichier est importé) plutôt que par scan de répertoire —
navigable par un IDE, ne peut pas être pollué par un fichier mal nommé, et les erreurs de
double-enregistrement sont détectées tout de suite plutôt que silencieusement ignorées.
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
    """Métadonnées déclaratives d'un module : id, s'il peut servir de source de
    classification, s'il peut produire un lien externe/Bioref, les domaines applicables, sa
    priorité (départage les égalités entre modules de classification concurrents — ex. GBIF
    999, ITIS 998, WoRMS 996), et s'il est la classification par défaut."""

    id: str
    can_classify: bool
    can_render_external_link: bool
    domains: DomainSpec
    priority: int = 0
    is_default_classification: bool = False


class TaxonomyModule(ABC):
    """Un module = un adaptateur pour une base taxonomique tierce. Toute la logique
    d'accès réseau/parsing du format d'échange doit vivre dans le sous-package
    `organon.modules.<id>.adapter`, jamais ici : cette classe ne porte que l'orchestration
    métier — un adaptateur isolé peut être remplacé ou corrigé (ex. changement de version
    d'API tierce) sans toucher à cette logique."""

    meta: ClassVar[ModuleMeta]

    @abstractmethod
    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collecte les données de ce module pour `struct.taxon`. Retourne le Struct mis à
        jour en cas de succès (le module peut avoir besoin de retourner un nouvel objet,
        p. ex. si le nom du taxon change suite au suivi d'un synonyme), ou None en cas
        d'échec."""
        raise NotImplementedError

    def render_bioref(self, struct: Struct) -> str | list[str] | None:
        """Rendu du modèle {{Bioref|...}} pour ce module. None = ce module ne contribue
        aucune entrée (comportement par défaut si le module n'a pas de rendu externe, ex.
        les modules 'fin'/'externe' internes)."""
        return None

    def debug_link(self, struct: Struct) -> str | None:
        """Lien brut affiché dans le panneau de debug."""
        return None


_REGISTRY: dict[str, TaxonomyModule] = {}


def register_module(cls: type[TaxonomyModule]) -> type[TaxonomyModule]:
    """Décorateur d'enregistrement. Usage : `@register_module` au-dessus d'une classe
    `TaxonomyModule` dotée d'un attribut de classe `meta`."""
    if not hasattr(cls, "meta"):
        raise TypeError(f"{cls.__name__} doit définir un attribut de classe 'meta' (ModuleMeta)")
    instance = cls()
    if instance.meta.id in _REGISTRY:
        raise ValueError(f"module '{instance.meta.id}' déjà enregistré")
    _REGISTRY[instance.meta.id] = instance
    return cls


def clear_registry() -> None:
    """Réservé aux tests unitaires (isolation entre modules factices)."""
    _REGISTRY.clear()


def all_modules() -> dict[str, TaxonomyModule]:
    return dict(_REGISTRY)


def get_module(module_id: str) -> TaxonomyModule | None:
    return _REGISTRY.get(module_id)


def classification_modules() -> list[str]:
    """Ids des modules pouvant servir de source de classification."""
    return [m.meta.id for m in _REGISTRY.values() if m.meta.can_classify]


def default_classification_module() -> str | None:
    """Id du module de classification par défaut, s'il y en a un."""
    for m in _REGISTRY.values():
        if m.meta.is_default_classification:
            return m.meta.id
    return None


def module_domain_trees(exclude: set[str] | None = None) -> dict[str, DomainTree]:
    """Construit l'arbre de domaines de chaque module enregistré, pour utilisation avec
    `organon.core.domains.modules_possibles`/`meilleure_classification`. `exclude` permet
    d'omettre des modules désactivés."""
    exclude = exclude or set()
    return {
        m.meta.id: build_module_domain_tree(m.meta.domains)
        for m in _REGISTRY.values()
        if m.meta.id not in exclude
    }


def module_priorities(exclude: set[str] | None = None) -> dict[str, int]:
    exclude = exclude or set()
    return {m.meta.id: m.meta.priority for m in _REGISTRY.values() if m.meta.id not in exclude}
