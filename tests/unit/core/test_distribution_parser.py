"""Parseur de la section « Répartition » d'un article frwiki (pur, sans réseau)."""

from __future__ import annotations

from pathlib import Path

import pytest

from organon.core.distribution_parser import parse_repartition

FIX = Path(__file__).parent / "fixtures" / "repartition"


def _fix(nom: str) -> str:
    return (FIX / f"{nom}.wiki").read_text(encoding="utf-8")


def test_section_simple():
    v = parse_repartition("intro\n== Répartition ==\nEn [[France]].\n== Autre ==\nHors zone.\n")
    assert v.section_identifiee and v.titres == ["Répartition"]
    assert "France" in v.texte and "Hors zone" not in v.texte
    assert v.wgsrpd is None


@pytest.mark.parametrize(
    "titre",
    ["Répartition géographique", "Distribution", "Habitat et répartition", "Aire de répartition",
     "RÉPARTITION", "Écologie et distribution"],
)
def test_titres_reconnus_par_mot_cle(titre):
    v = parse_repartition(f"== {titre} ==\nEn [[Inde]].\n== Fin ==\nx\n")
    assert v.section_identifiee and "Inde" in v.texte


def test_titre_sans_mot_cle_jamais_devine():
    v = parse_repartition("== Habitat, écologie ==\nEn [[Inde]].\n")
    assert not v.section_identifiee and v.texte == ""


def test_sous_sections_incluses_jusqu_au_titre_de_meme_niveau():
    wt = (
        "== Répartition géographique ==\nA [[Chine]].\n=== Répartition ancienne ===\nB [[Inde]].\n"
        "==== Détail ====\nC [[Iran]].\n=== Répartition actuelle ===\nD [[Népal]].\n"
        "== Habitat ==\nE [[Brésil]].\n"
    )
    v = parse_repartition(wt)
    assert all(p in v.texte for p in ("Chine", "Inde", "Iran", "Népal"))
    assert "Brésil" not in v.texte


def test_section_imbriquee_sous_titre_englobant_pris_une_fois():
    wt = "== Écologie et répartition ==\n=== Habitat ===\nA.\n=== Répartition ===\nB [[Inde]].\n== Fin ==\n"
    v = parse_repartition(wt)
    assert v.texte.count("Inde") == 1 and "A." in v.texte


def test_deux_sections_disjointes_concatenees():
    v = parse_repartition("== Répartition ==\nA [[Chine]].\n== X ==\nz\n== Distribution ==\nB [[Inde]].\n")
    assert "Chine" in v.texte and "Inde" in v.texte and len(v.titres) == 2


def test_refs_et_commentaires_retires():
    v = parse_repartition(
        "== Répartition ==\nEn [[Inde]]<ref>Norvège</ref><ref name=a/> <!-- Chine -->.\n"
    )
    assert "Norvège" not in v.texte and "Chine" not in v.texte and "Inde" in v.texte


def test_gabarit_wgsrpd_par_statut_et_retire_du_texte():
    wt = (
        "== Répartition ==\n{{WGSRPD|certain=FRA, ITA|incertain=LEE|introduit=ABT|eteint=NZS"
        "|source=[[Plants of the World Online|POWO]]{{Bioref|powo|6 août 2026|ref}}}}\nEn [[Italie]].\n"
    )
    v = parse_repartition(wt)
    assert v.wgsrpd == {
        "certain": frozenset({"FRA", "ITA"}),
        "incertain": frozenset({"LEE"}),
        "introduit": frozenset({"ABT"}),
        "eteint": frozenset({"NZS"}),
    }
    assert "WGSRPD" not in v.texte and "Plants of the World" not in v.texte
    assert "Italie" in v.texte


def test_gabarit_wgsrpd_hors_section_repartition_trouve():
    v = parse_repartition("== Histoire ==\n{{WGSRPD|certain=CHN}}\n== Autre ==\n")
    assert not v.section_identifiee
    assert v.wgsrpd == {
        "certain": frozenset({"CHN"}), "incertain": frozenset(),
        "introduit": frozenset(), "eteint": frozenset(),
    }


def test_gabarit_vide_reconnu_comme_present():
    v = parse_repartition("{{WGSRPD|source=x}}")
    assert v.wgsrpd is not None and not any(v.wgsrpd.values())


def test_article_sans_rien():
    v = parse_repartition("== Description ==\ntexte\n")
    assert not v.section_identifiee and v.wgsrpd is None and v.titres == []


def test_fixture_metaxya_gabarit_et_prose():
    v = parse_repartition(_fix("Metaxya"))
    assert v.titres == ["Répartition"]
    assert v.wgsrpd is not None and "LEE" in v.wgsrpd["incertain"]
    assert len(v.wgsrpd["certain"]) == 18
    assert "Suriname" in v.texte and "Liste des espèces" not in v.texte


def test_fixture_setaria_gabarit_hors_section():
    v = parse_repartition(_fix("Setaria_italica"))
    assert not v.section_identifiee
    assert v.wgsrpd is not None and v.wgsrpd["certain"] == {"CHN", "CHS"}
    assert "ABT" in v.wgsrpd["introduit"]


def test_fixture_rosa_canina_prose_a_puces():
    v = parse_repartition(_fix("Rosa_canina"))
    assert v.titres == ["Répartition"] and v.wgsrpd is None
    assert "Tadjikistan" in v.texte and "Variétés" not in v.texte
    assert "neutrocalcicole" in v.texte  # sous-section incluse


def test_fixture_lion_sous_sections():
    v = parse_repartition(_fix("Lion"))
    assert v.titres == ["Répartition géographique"]
    assert "Habitat, écologie" not in v.texte


def test_fixture_tigre_titre_englobant():
    v = parse_repartition(_fix("Tigre"))
    assert v.titres == ["Écologie et répartition"]


def test_fixture_canis_lupus_titre_long():
    v = parse_repartition(_fix("Canis_lupus"))
    assert v.titres and v.titres[0].startswith("Répartition et conservation")


@pytest.mark.parametrize("nom", ["Tyrannosaurus", "Éléphant_d_Afrique"])
def test_fixtures_sans_section(nom):
    v = parse_repartition(_fix(nom))
    assert not v.section_identifiee and v.texte == ""


def test_fixture_mentha_gabarit_dans_section():
    v = parse_repartition(_fix("Mentha_spicata"))
    assert v.titres == ["Répartition et habitats"]
    assert v.wgsrpd is not None and "AFG" in v.wgsrpd["certain"] and "ABT" in v.wgsrpd["introduit"]
    assert "Turquie" in v.texte
