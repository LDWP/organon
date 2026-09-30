"""Comparateur des taxons inférieurs article/source (pur, sans réseau)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.rendering.sections import render_lower_taxa
from organon.core.subtaxa_diagnosis import compare_subtaxa, diagnose_subtaxa
from organon.core.subtaxa_parser import parse_sous_taxons


def _types(article, source, **kw):
    kw.setdefault("source", "COL")
    kw.setdefault("truncated", False)
    return [e.type for e in diagnose_subtaxa(article, source, **kw)]


def test_ensembles_identiques_zero_ecart():
    assert diagnose_subtaxa(["A a", "B b"], ["B b", "A a"], source="COL", truncated=False) == []


def test_source_plus_riche_absent_article_info():
    ecarts = diagnose_subtaxa(["A a"], ["A a", "B b", "C c"], source="COL", truncated=False)
    assert [(e.type, e.severite, e.source) for e in ecarts] == [
        ("sous_taxon_absent_article", "info", "COL")
    ]
    assert "B b" in ecarts[0].message and "C c" in ecarts[0].message
    assert ecarts[0].valeur_source == "B b, C c" and ecarts[0].valeur_wikidata is None


def test_article_plus_riche_absent_source_info():
    ecarts = diagnose_subtaxa(["A a", "B b"], ["A a"], source="COL", truncated=False)
    assert [(e.type, e.severite) for e in ecarts] == [("sous_taxon_absent_source", "info")]
    assert ecarts[0].valeur_wikidata == "B b" and ecarts[0].valeur_source is None


def test_comptes_pour_l_affichage_liste_a_cinq():
    d = compare_subtaxa(["A a", "B b", "C c"], ["A a", "B b", "C c", "D d", "E e"],
                        source="COL", truncated=False)
    assert d.comptes is not None
    assert (d.comptes.n_article, d.comptes.n_source) == (3, 5)
    assert d.comptes.absents_article == ["D d", "E e"] and d.comptes.absents_source == []
    assert d.limites == []


def test_liste_source_tronquee_aucun_ecart_limite_exposee():
    d = compare_subtaxa(["A a"], ["B b"], source="COL", truncated=True)
    assert d.ecarts == [] and d.comptes is None and len(d.limites) == 1


def test_zone_non_identifiee_aucun_ecart_limite_exposee():
    d = compare_subtaxa(None, ["B b"], source="COL", truncated=False)
    assert d.ecarts == [] and d.comptes is None and len(d.limites) == 1


def test_source_muette_jamais_un_ecart():
    assert _types(["A a"], []) == []


def test_espaces_normalises():
    assert _types(["A  a"], ["A a "]) == []


@pytest.mark.parametrize("n", [3, 40])
def test_aller_retour_render_inf_reparse_zero_ecart(n):
    genres = [
        RankName(name=f"Genus{chr(97 + i % 26)}{i}", rank="genre", author="Linnaeus, 1758",
                 extinct=(i % 7 == 0))
        for i in range(n)
    ]
    espece = RankName(name="Falco peregrinus", rank="espèce", author="Tunstall, 1771")
    struct = Struct(
        taxon=TaxonInfo(name="Falconidae", rank="famille"),
        kingdom="animal",
        subtaxa=SubTaxonList(items=[*genres, espece], source="COL"),
    )
    rendu = render_lower_taxa(struct, GenerateOptions())
    vue = parse_sous_taxons(rendu)
    assert vue is not None
    assert set(vue.noms) == {s.name for s in struct.subtaxa.items}
    assert diagnose_subtaxa(vue.noms, [s.name for s in struct.subtaxa.items],
                            source="COL", truncated=False) == []
