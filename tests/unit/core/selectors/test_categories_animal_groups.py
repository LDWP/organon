"""Large animal groups get a precise category instead of the generic kingdom one."""

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, TaxonInfo
from organon.core.selectors.categorization import link_for_category

_GROUPS = [
    ("classe", "Bivalvia", "de bivalves"),
    ("classe", "Gastropoda", "de gastéropodes"),
    ("classe", "Insecta", "d'insectes"),
    ("classe", "Arachnida", "d'arachnides"),
    ("classe", "Aves", "d'oiseaux"),
    ("classe", "Mammalia", "de mammifères"),
    ("embranchement", "Echinodermata", "d'échinodermes"),
]
_RANKS = [("espèce", "Espèce"), ("genre", "Genre"), ("famille", "Famille")]


def _struct(group_rank: str, group: str, rank: str) -> Struct:
    return Struct(
        taxon=TaxonInfo(name="Taxon", rank=rank),
        kingdom="animal",
        ranks=[RankName(name="Higher", rank="ordre"), RankName(name=group, rank=group_rank)],
    )


@pytest.mark.parametrize(("group_rank", "group", "label"), _GROUPS)
@pytest.mark.parametrize(("rank", "prefix"), _RANKS)
def test_group_category_replaces_generic_animal_category(group_rank, group, label, rank, prefix):
    result = link_for_category(_struct(group_rank, group, rank), GenerateOptions())
    assert result == [f"{prefix} {label} (nom scientifique)"]


def test_other_rank_in_a_listed_group_falls_back_to_kingdom_category():
    result = link_for_category(_struct("classe", "Aves", "ordre"), GenerateOptions())
    assert result == ["Animal (nom scientifique)"]


def test_selectors_disabled_keeps_generic_category():
    result = link_for_category(
        _struct("classe", "Aves", "espèce"), GenerateOptions(selectors=False)
    )
    assert result == ["Animal (nom scientifique)"]
