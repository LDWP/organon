"""Moteur de règles sûr pour la catégorisation (ébauches/catégories/portails) : un fichier de
règles ne doit jamais pouvoir faire exécuter du code arbitraire, y compris s'il vient à
contenir du texte non maîtrisé. Le corpus de règles nécessaire se limite entièrement à des
égalités simples combinées par ET/OU ; ce module implémente donc un petit évaluateur d'arbre
de conditions typé (Pydantic), capable d'exprimer exactement ce corpus sans jamais recourir à
`eval()` ou équivalent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml
from pydantic import BaseModel, Field, RootModel

from organon.core.models import Struct

RULES_DIR = Path(__file__).resolve().parent / "rules"


class FieldEq(BaseModel):
    field: str
    eq: str


class AllOf(BaseModel):
    all_of: list["Condition"]


class AnyOf(BaseModel):
    any_of: list["Condition"]


Condition = Union[FieldEq, AllOf, AnyOf]


class Rule(BaseModel):
    when: Condition
    return_: list[str] = Field(alias="return")

    model_config = {"populate_by_name": True}


class RuleSet(RootModel[list[Rule]]):
    pass


AllOf.model_rebuild()
AnyOf.model_rebuild()


def resolve_field(struct: Struct, field: str) -> str | None:
    """Résout un jeton 'regne' / 'classification' / 'rang' / 'rangs.<rang>' contre le Struct.
    Retourne None si non résolvable — jamais égal à une valeur de règle réelle, donc une
    condition sur un jeton non résolvable ne matche jamais silencieusement."""
    if field == "regne":
        return struct.regne
    if field == "classification":
        return struct.classification
    if field == "rang":
        return struct.taxon.rang
    if field == "milieu":
        return struct.milieu
    if field.startswith("rangs."):
        rang_id = field[len("rangs.") :]
        for r in struct.rangs:
            if r.rang == rang_id:
                return r.nom
        return None
    return None


def _evaluate(condition: Condition, struct: Struct) -> bool:
    if isinstance(condition, FieldEq):
        return resolve_field(struct, condition.field) == condition.eq
    if isinstance(condition, AllOf):
        return all(_evaluate(c, struct) for c in condition.all_of)
    if isinstance(condition, AnyOf):
        return any(_evaluate(c, struct) for c in condition.any_of)
    raise TypeError(f"condition inconnue : {condition!r}")


def load_ruleset(name: str) -> RuleSet | None:
    """Charge `rules/<name>.local.yaml` s'il existe (permet de surcharger localement les
    règles par défaut sans les modifier), sinon `rules/<name>.yaml`. Retourne None si aucun
    des deux n'existe."""
    for candidate in (RULES_DIR / f"{name}.local.yaml", RULES_DIR / f"{name}.yaml"):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or []
            return RuleSet.model_validate(raw)
    return None


def evaluate_ruleset(name: str, struct: Struct) -> list[str] | None:
    """Évalue les règles dans l'ordre, retourne le `return` de la première qui matche, ou
    None si aucune. Si le taxon n'a pas encore de classification (`struct.rangs` vide), aucune
    règle n'est évaluée."""
    if not struct.rangs:
        return None
    ruleset = load_ruleset(name)
    if ruleset is None:
        return None
    for rule in ruleset.root:
        if _evaluate(rule.when, struct):
            return rule.return_
    return None
