"""Safe rule engine for stubs, categories and portals.

Rule files must never run arbitrary code. The corpus only needs
equalities combined by AND/OR, so a small typed condition tree
(Pydantic) is evaluated, never `eval()`.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, RootModel

from organon.core.models import Struct

RULES_DIR = Path(__file__).resolve().parent / "rules"


class FieldEq(BaseModel):
    """Condition: a struct field equals a value."""

    field: str
    eq: str


class AllOf(BaseModel):
    """Condition: all sub-conditions hold."""

    all_of: list[Condition]


class AnyOf(BaseModel):
    """Condition: at least one sub-condition holds."""

    any_of: list[Condition]


Condition = FieldEq | AllOf | AnyOf


class Rule(BaseModel):
    """A condition and the list returned when it matches."""

    when: Condition
    return_: list[str] = Field(alias="return")

    model_config = {"populate_by_name": True}


class RuleSet(RootModel[list[Rule]]):
    """Ordered list of rules."""

    pass


AllOf.model_rebuild()
AnyOf.model_rebuild()


def resolve_field(struct: Struct, field: str) -> str | None:
    """Resolve a field token against the struct.

    Tokens: regne, classification, rang, milieu, rangs.<rang>. None if
    unresolvable, so a condition on it never matches.
    """
    if field == "regne":
        return struct.kingdom
    if field == "classification":
        return struct.classification
    if field == "rang":
        return struct.taxon.rank
    if field == "milieu":
        return struct.habitat
    if field.startswith("rangs."):
        rank_id = field[len("rangs.") :]
        for r in struct.ranks:
            if r.rank == rank_id:
                return r.name
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


@cache
def load_ruleset(name: str) -> RuleSet | None:
    """Load `rules/<name>.local.yaml` if present, else `<name>.yaml`.

    The local file overrides the defaults. None if neither exists.
    Cached: the files do not change during a run.
    """
    for candidate in (RULES_DIR / f"{name}.local.yaml", RULES_DIR / f"{name}.yaml"):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or []
            return RuleSet.model_validate(raw)
    return None


def evaluate_ruleset(name: str, struct: Struct) -> list[str] | None:
    """Return the `return` of the first matching rule, else None.

    No rule is evaluated while `struct.ranks` is empty.
    """
    if not struct.ranks:
        return None
    ruleset = load_ruleset(name)
    if ruleset is None:
        return None
    for rule in ruleset.root:
        if _evaluate(rule.when, struct):
            return rule.return_
    return None
