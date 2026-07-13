"""Arbre des domaines (règne / sous-groupe) et logique de correspondance module/domaine.

Note sur `meilleure_classification`/`rec_prof_classification` : le score de profondeur
additionne un bonus `cnt/20` (nombre de domaines frères acceptés par le module), puis
`meilleure_classification` retient le score le PLUS PETIT. Au sein d'une même requête de
domaine, le terme de profondeur de base est identique pour tous les modules comparés (même
topologie d'arbre) — seul ce bonus diffère selon le module. Prendre le score minimal revient
donc à préférer le module ayant le moins de domaines frères acceptés, donc le plus spécialisé.
Contre-intuitif à première lecture (on pourrait s'attendre à maximiser un score de
spécialisation), mais le comportement est correct et testé : ne pas "corriger" ce sens de tri.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DomainSpec = Literal["all", "none"] | list[str]
"""Domaines couverts par un module : 'all' (tous), 'none' (aucun), ou une liste explicite de
noms de domaines."""


@dataclass
class DomainNode:
    accepte: bool
    sous: dict[str, "DomainNode"] = field(default_factory=dict)

    def copy(self) -> "DomainNode":
        return DomainNode(accepte=self.accepte, sous={k: v.copy() for k, v in self.sous.items()})


DomainTree = dict[str, DomainNode]


def _base_tree(accepte: bool) -> DomainTree:
    """Construit un arbre de domaines entièrement accepté ou entièrement refusé."""
    return {
        "algue": DomainNode(accepte),
        "animal": DomainNode(
            accepte,
            sous={
                "oiseau": DomainNode(accepte),
                "reptile": DomainNode(accepte),
                "poisson": DomainNode(accepte),
                "mammifère": DomainNode(accepte),
                "amphibien": DomainNode(accepte),
            },
        ),
        "archaea": DomainNode(accepte),
        "bactérie": DomainNode(accepte),
        "champignon": DomainNode(accepte),
        "protiste": DomainNode(accepte),
        "végétal": DomainNode(accepte),
        "virus": DomainNode(accepte),
        "neutre": DomainNode(accepte),
        "eucaryote": DomainNode(accepte),
        "procaryote": DomainNode(accepte),
    }


DOMAINES_TRUE: DomainTree = _base_tree(True)
DOMAINES_FALSE: DomainTree = _base_tree(False)


def _collect_all_domains(tree: DomainTree, out: set[str]) -> None:
    for name, node in tree.items():
        out.add(name)
        _collect_all_domains(node.sous, out)


TOUS_DOMAINES: set[str] = set()
_collect_all_domains(DOMAINES_TRUE, TOUS_DOMAINES)


def rec_domaines(domaine: DomainTree, nom: str, val: bool) -> None:
    """Porte rec_domaines() : positionne `val` sur l'entrée `nom` (ou toutes si nom == '*')
    et propage récursivement à tous ses descendants."""
    for id_, node in domaine.items():
        if nom == "*" or id_ == nom:
            node.accepte = val
            if node.sous:
                rec_domaines(node.sous, "*", val)
        else:
            rec_domaines(node.sous, nom, val)


def creer_domaines(par_defaut_tous: bool, liste: list[str]) -> DomainTree:
    """Porte creer_domaines(). Si par_defaut_tous est True, tous les domaines sont acceptés
    sauf ceux listés (qui sont refusés) ; si False (cas d'usage réel de declare_module),
    tous les domaines sont refusés sauf ceux listés (qui sont acceptés, avec leurs
    descendants)."""
    if par_defaut_tous:
        tree = {k: v.copy() for k, v in DOMAINES_TRUE.items()}
        val = False
    else:
        tree = {k: v.copy() for k, v in DOMAINES_FALSE.items()}
        val = True
    for d in liste:
        rec_domaines(tree, d, val)
    return tree


def build_module_domain_tree(domains: DomainSpec) -> DomainTree:
    """Équivalent du calcul de `$blob['domaines']` dans declare_module()."""
    if domains == "all":
        return {k: v.copy() for k, v in DOMAINES_TRUE.items()}
    if domains == "none":
        return {k: v.copy() for k, v in DOMAINES_FALSE.items()}
    return creer_domaines(False, domains)


def vrai_dans_domaine(def_: DomainTree) -> bool:
    if not def_:
        return False
    for node in def_.values():
        if node.accepte:
            return True
        if vrai_dans_domaine(node.sous):
            return True
    return False


def rec_contenu_domaine(domaine: str, def_: DomainTree) -> DomainNode | None:
    for nom, node in def_.items():
        if nom == domaine:
            return node
        found = rec_contenu_domaine(domaine, node.sous)
        if found is not None:
            return found
    return None


def rec_strict_domaine(domaine: str, def_: DomainTree) -> bool:
    for nom, node in def_.items():
        if nom == domaine and node.accepte:
            return True
        if rec_strict_domaine(domaine, node.sous):
            return True
    return False


def modules_possibles(domaine: str, module_trees: dict[str, DomainTree]) -> list[str] | None:
    """`module_trees` associe id-module -> son arbre de domaines. Retourne None si le domaine
    demandé n'existe pas du tout dans `TOUS_DOMAINES`."""
    if domaine != "*" and domaine not in TOUS_DOMAINES:
        return None

    if domaine == "*":
        return list(module_trees.keys())

    out = []
    for nom, tree in module_trees.items():
        if rec_strict_domaine(domaine, tree):
            out.append(nom)
            continue
        base = rec_contenu_domaine(domaine, tree)
        if base is not None and vrai_dans_domaine({"anonymous": base}):
            out.append(nom)
    return out


def rec_prof_classification(def_: DomainTree, domaine: str, prof: int) -> float:
    ret = 0.0
    cnt = sum(1 for node in def_.values() if node.accepte)
    for id_, node in def_.items():
        ret2 = 0.0
        if (domaine == "*" or id_ == domaine) and node.accepte:
            ret = prof + 1
            ret += cnt / 20.0
        else:
            ret2 = rec_prof_classification(node.sous, "*", prof + 1)
        if ret2 > ret:
            ret = ret2
    return ret


def profondeur_classification(module_tree: DomainTree, domaine: str) -> float:
    return rec_prof_classification(module_tree, domaine, 0)


def profondeur_domaine(def_: DomainTree, domaine: str, prof: int) -> int:
    for nom, node in def_.items():
        if nom == domaine:
            return prof + 1
        ret = profondeur_domaine(node.sous, domaine, prof + 1)
        if ret == 0:
            continue
        if ret > prof:
            return ret
    return 0


def meilleure_classification(
    domaine: str,
    classification_module_ids: list[str],
    module_trees: dict[str, DomainTree],
    module_priorities: dict[str, int],
    default_module: str | None,
) -> str | None:
    """`classification_module_ids` = modules pouvant servir de source de classification ;
    `module_trees` = arbre de domaines par module ; `module_priorities` = niveau de priorité
    par module ; `default_module` = module de classification par défaut."""
    if domaine == "*":
        return default_module

    if not classification_module_ids:
        return None
    if len(classification_module_ids) == 1:
        return classification_module_ids[0]

    prof = profondeur_domaine(DOMAINES_TRUE, domaine, 0)  # noqa: F841 (calculé pour l'invariant ci-dessus, jamais réutilisé ensuite)

    scored: dict[str, float] = {}
    for c in classification_module_ids:
        val = profondeur_classification(module_trees[c], domaine)
        if val > 0:
            scored[c] = val

    if not scored:
        return default_module
    if len(scored) == 1:
        return next(iter(scored))

    min_val = min(scored.values())
    tied = [nom for nom, val in scored.items() if val == min_val]
    if len(tied) == 1:
        return tied[0]

    if default_module in tied:
        return default_module

    # tri par niveau de préférence décroissant, on prend le plus haut
    tied_by_priority = sorted(tied, key=lambda nom: module_priorities.get(nom, 0), reverse=True)
    return tied_by_priority[0]


# Correspondance règne (tiers) -> domaine Organon, partagée par tous les modules plutôt que
# dupliquée par module : une table explicite et facile à éditer. "Chromista" -> "protiste"
# (et non "algue") reflète la correction appliquée en 2023 suite au bug remonté sur les
# ciliés/foraminifères.
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
