"""Domain tree (kingdom / subgroup) and module-domain matching.

`best_classification` keeps the LOWEST depth score. Within one
query only the sibling bonus `cnt/20` differs between modules, so
the minimum prefers the most specialized module. Do not flip it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Domains a module covers: 'all', 'none' or an explicit list of names.
DomainSpec = Literal["all", "none"] | list[str]


@dataclass
class DomainNode:
    """Domain tree node; `accepted` tells if the module covers it."""

    accepted: bool
    children: dict[str, DomainNode] = field(default_factory=dict)

    def copy(self) -> DomainNode:
        """Return a deep copy of the subtree."""
        return DomainNode(
            accepted=self.accepted, children={k: v.copy() for k, v in self.children.items()}
        )


DomainTree = dict[str, DomainNode]


def _base_tree(accepted: bool) -> DomainTree:
    """Build a domain tree with every domain accepted or rejected."""
    return {
        "algue": DomainNode(accepted),
        "animal": DomainNode(
            accepted,
            children={
                "oiseau": DomainNode(accepted),
                "reptile": DomainNode(accepted),
                "poisson": DomainNode(accepted),
                "mammifère": DomainNode(accepted),
                "amphibien": DomainNode(accepted),
                "arachnide": DomainNode(accepted),
            },
        ),
        "archaea": DomainNode(accepted),
        "bactérie": DomainNode(accepted),
        "champignon": DomainNode(accepted),
        "protiste": DomainNode(accepted),
        "végétal": DomainNode(accepted),
        "virus": DomainNode(accepted),
        "neutre": DomainNode(accepted),
        "eucaryote": DomainNode(accepted),
        "procaryote": DomainNode(accepted),
    }


ALL_ACCEPTED_TREE: DomainTree = _base_tree(True)
_NONE_ACCEPTED_TREE: DomainTree = _base_tree(False)


def _collect_all_domains(tree: DomainTree, out: set[str]) -> None:
    for name, node in tree.items():
        out.add(name)
        _collect_all_domains(node.children, out)


_ALL_DOMAIN_NAMES: set[str] = set()
_collect_all_domains(ALL_ACCEPTED_TREE, _ALL_DOMAIN_NAMES)


def _set_domain(domain: DomainTree, name: str, val: bool) -> None:
    """Set `val` on entry `nom` (all if '*') and its descendants."""
    for id_, node in domain.items():
        if name == "*" or id_ == name:
            node.accepted = val
            if node.children:
                _set_domain(node.children, "*", val)
        else:
            _set_domain(node.children, name, val)


def _create_domains(all_by_default: bool, listed: list[str]) -> DomainTree:
    """Build a tree from a list of domains.

    If `all_by_default`, all domains are accepted except the listed
    ones; otherwise all are rejected except the listed ones and their
    descendants.
    """
    if all_by_default:
        tree = {k: v.copy() for k, v in ALL_ACCEPTED_TREE.items()}
        val = False
    else:
        tree = {k: v.copy() for k, v in _NONE_ACCEPTED_TREE.items()}
        val = True
    for d in listed:
        _set_domain(tree, d, val)
    return tree


def build_module_domain_tree(domains: DomainSpec) -> DomainTree:
    """Build the domain tree of a module from its `domains`."""
    if domains == "all":
        return {k: v.copy() for k, v in ALL_ACCEPTED_TREE.items()}
    if domains == "none":
        return {k: v.copy() for k, v in _NONE_ACCEPTED_TREE.items()}
    return _create_domains(False, domains)


def _any_accepted(domain_tree: DomainTree) -> bool:
    """Return True if any node of the tree is accepted."""
    if not domain_tree:
        return False
    for node in domain_tree.values():
        if node.accepted:
            return True
        if _any_accepted(node.children):
            return True
    return False


def _find_domain_node(domain: str, domain_tree: DomainTree) -> DomainNode | None:
    """Return the node named `domaine`, or None."""
    for name, node in domain_tree.items():
        if name == domain:
            return node
        found = _find_domain_node(domain, node.children)
        if found is not None:
            return found
    return None


def _is_strictly_accepted(domain: str, domain_tree: DomainTree) -> bool:
    """Return True if `domaine` itself is accepted."""
    for name, node in domain_tree.items():
        if name == domain and node.accepted:
            return True
        if _is_strictly_accepted(domain, node.children):
            return True
    return False


def domain_covers(domain: str, domain_tree: DomainTree) -> bool:
    """Return True if the tree covers `domaine`.

    True when `domaine` or one of its sub-domains is accepted, e.g.
    "animal" for a module restricted to "mammifère".
    """
    if _is_strictly_accepted(domain, domain_tree):
        return True
    base = _find_domain_node(domain, domain_tree)
    return base is not None and _any_accepted({"anonymous": base})


def possible_modules(domain: str, module_trees: dict[str, DomainTree]) -> list[str] | None:
    """Return the ids of modules covering `domaine`.

    `module_trees` maps module id to its tree. None if `domaine` is
    unknown.
    """
    if domain != "*" and domain not in _ALL_DOMAIN_NAMES:
        return None

    if domain == "*":
        return list(module_trees.keys())

    return [name for name, tree in module_trees.items() if domain_covers(domain, tree)]


def _classification_depth_from(domain_tree: DomainTree, domain: str, depth: int) -> float:
    """Return the depth score of `domaine` in the tree."""
    ret = 0.0
    count = sum(1 for node in domain_tree.values() if node.accepted)
    for id_, node in domain_tree.items():
        ret2 = 0.0
        if (domain == "*" or id_ == domain) and node.accepted:
            ret = depth + 1
            ret += count / 20.0
        else:
            ret2 = _classification_depth_from(node.children, domain, depth + 1)
        if ret2 > ret:
            ret = ret2
    return ret


def _classification_depth(module_tree: DomainTree, domain: str) -> float:
    """Return the depth score of `domaine` for one module."""
    return _classification_depth_from(module_tree, domain, 0)


def best_classification(
    domain: str,
    classification_module_ids: list[str],
    module_trees: dict[str, DomainTree],
    module_priorities: dict[str, int],
    default_module: str | None,
) -> str | None:
    """Pick the classification module best suited to `domaine`.

    Ties go to `default_module`, then to the highest priority.
    """
    if domain == "*":
        return default_module

    if not classification_module_ids:
        return None
    if len(classification_module_ids) == 1:
        return classification_module_ids[0]

    scored: dict[str, float] = {}
    for c in classification_module_ids:
        val = _classification_depth(module_trees[c], domain)
        if val > 0:
            scored[c] = val

    if not scored:
        return default_module
    if len(scored) == 1:
        return next(iter(scored))

    min_val = min(scored.values())
    tied = [name for name, val in scored.items() if val == min_val]
    if len(tied) == 1:
        return tied[0]

    if default_module in tied:
        return default_module

    # highest priority first
    tied_by_priority = sorted(tied, key=lambda name: module_priorities.get(name, 0), reverse=True)
    return tied_by_priority[0]


# Third-party kingdom -> Organon domain, shared by all modules.
KINGDOM_MAP: dict[str, str] = {
    "Animalia": "animal",
    "Plantae": "végétal",
    "Viridiplantae": "végétal",
    "Fungi": "champignon",
    "Chromista": "protiste",
    "Protozoa": "protiste",
    "Protista": "protiste",
    "Bacteria": "bactérie",
    "Eubacteria": "bactérie",
    "Archaea": "archaea",
    "Archaebacteria": "archaea",
    "Viruses": "virus",
}

# ChecklistBank `domain` rank -> Organon domain. `kingdom` is unstable
# for prokaryotes (renamed GTDB clades), `domain` is not.
DOMAIN_MAP: dict[str, str] = {
    "Bacteria": "bactérie",
    "Archaea": "archaea",
}


def kingdom_from_classification(classification: list[dict]) -> str:
    """Resolve the Organon kingdom from a ChecklistBank chain.

    Use the stable `domain` rank for prokaryotes, else `kingdom`.
    Return "" if neither is recognized.
    """
    domain_name = next((c.get("name") for c in classification if c.get("rank") == "domain"), None)
    if domain_name in DOMAIN_MAP:
        return DOMAIN_MAP[domain_name]
    kingdom_name = next(
        (c.get("name") for c in classification if c.get("rank") == "kingdom"), None
    )
    return KINGDOM_MAP.get(kingdom_name, "") if kingdom_name else ""
