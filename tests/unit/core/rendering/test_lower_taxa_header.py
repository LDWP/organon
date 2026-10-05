"""En-tête de la liste des taxons inférieurs selon le rang du taxon décrit."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.rendering.sections import render_lower_taxa


def _header(name: str, rank: str, kingdom: str, items: list[RankName], source: str = "WFO") -> str:
    struct = Struct(
        taxon=TaxonInfo(name=name, rank=rank),
        kingdom=kingdom,
        subtaxa=SubTaxonList(items=items, source=source),
    )
    lines = render_lower_taxa(struct, GenerateOptions()).splitlines()
    return lines[lines.index("== Liste des " + _title(items) + " ==") + 1]


def _title(items: list[RankName]) -> str:
    from organon.core.rendering.sections import compute_rank_text

    return compute_rank_text(items)[0]


GENRES = [RankName(name="Blasia", rank="genre"), RankName(name="Cavicularia", rank="genre")]


def test_famille_vegetale_phrase_complete():
    header = _header("Blasiaceae", "famille", "plante", GENRES)
    assert header.startswith("Selon {{Bioref|WFO|")
    assert header.endswith("}}, la famille des ''Blasiaceae'' comprend les genres suivants :")


def test_tribu_feminin_et_pluriel_du_rang_des_sous_taxons():
    items = [RankName(name="Aaa", rank="sous-tribu"), RankName(name="Bbb", rank="sous-tribu")]
    header = _header("Xxxeae", "tribu", "plante", items)
    assert header.endswith("}}, la tribu des ''Xxxeae'' comprend les sous-tribus suivantes :")


def test_ordre_et_sous_famille():
    assert _header("Xxxales", "ordre", "plante", GENRES).endswith(
        "}}, l'ordre des ''Xxxales'' comprend les genres suivants :"
    )
    assert _header("Xxxoideae", "sous-famille", "plante", GENRES).endswith(
        "}}, la sous-famille des ''Xxxoideae'' comprend les genres suivants :"
    )


def test_rangs_mixtes_listes_avec_et():
    items = [*GENRES, RankName(name="Sect", rank="section")]
    header = _header("Blasiaceae", "famille", "plante", items)
    assert header.endswith("comprend les genres et sections suivants :")


@pytest.mark.parametrize("rank", ["genre", "sous-genre", "espèce"])
def test_rang_genre_ou_inferieur_garde_la_forme_actuelle(rank):
    items = [RankName(name="Aaa bbb", rank="espèce")]
    header = _header("Aaa", rank, "plante", items)
    assert header.startswith("Selon {{Bioref|WFO|") and header.endswith("}} :")
    assert "comprend" not in header
