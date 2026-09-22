"""Contrat unique des fonctions de rang : `str | None`, `None` = rang inconnu (jamais un
sentinelle `"NOTFOUND"`/`"NOTFOUND-{rang}"`/`"non classé"` qui passerait les contrôles d'un
consommateur et finirait dans le wikitexte)."""

from __future__ import annotations

import pytest

from organon.core.models import RankName, Struct, TaxonInfo
from organon.core.rendering.grammar import (
    load_rank_table,
    wp_definite_rank,
    wp_extinct_rank,
    wp_indefinite_rank,
    wp_is_species_or_below,
    wp_rank_name,
)
from organon.core.rendering.sections import compute_rank_lines
from organon.modules.col_xr.ranks import col_xr_to_wp_rank
from organon.modules.indexfungorum.ranks import indexfungorum_to_wp_rank
from organon.modules.irmng.ranks import irmng_to_wp_rank
from organon.modules.tpdb.ranks import tpdb_to_wp_rank
from organon.modules.wrms.ranks import wrms_to_wp_rank

_INCONNU = "RangInexistantXyz"


@pytest.mark.parametrize("fonction", [wrms_to_wp_rank, irmng_to_wp_rank, tpdb_to_wp_rank, indexfungorum_to_wp_rank])
def test_rang_inconnu_est_none(fonction):
    assert fonction(_INCONNU) is None


@pytest.mark.parametrize("fonction", [wrms_to_wp_rank, irmng_to_wp_rank])
def test_rang_inconnu_ne_fuite_pas_dans_la_taxobox(fonction):
    struct = Struct(
        taxon=TaxonInfo(name="Foo bar", rank="espèce"),
        ranks=[RankName(name="Foo", rank=fonction(_INCONNU))],
        kingdom="animal",
    )
    wikitexte = "\n".join(ligne for _, _, ligne in compute_rank_lines(struct))
    assert "NOTFOUND-" not in wikitexte
    assert _INCONNU not in wikitexte


def test_col_xr_rang_inconnu_est_none():
    assert col_xr_to_wp_rank(_INCONNU) is None


def test_col_xr_non_classe_est_un_rang_valide_de_ranks_yaml():
    rang = col_xr_to_wp_rank("unranked")
    assert rang in load_rank_table().ranks


def test_grammaire_rang_inconnu_est_none():
    assert wp_rank_name(None, link=False, capitalize=False, plural=False) is None
    assert wp_rank_name(_INCONNU, link=True, capitalize=False, plural=False) is None
    assert wp_indefinite_rank(_INCONNU) is None
    assert wp_definite_rank(_INCONNU) is None
    assert wp_is_species_or_below(_INCONNU) is None
    assert wp_extinct_rank(_INCONNU) is None
