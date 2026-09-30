"""Parseur des liens externes d'un article frwiki (pur, sans réseau)."""

from __future__ import annotations

from pathlib import Path

from organon.core.wikilinks_parser import (
    CategoriePrincipale,
    parse_autres_projets,
    parse_bases,
    parse_categorie_principale,
)

FIXTURES = Path(__file__).parent / "fixtures" / "wikilinks"


def _article(nom: str) -> str:
    return (FIXTURES / f"{nom}.wiki").read_text(encoding="utf-8")


def test_autres_projets_multiligne_reel():
    projets = parse_autres_projets(_article("Lion"))
    assert projets["commons"].startswith("Category:")
    assert {"wikibooks", "wikiquote"} <= set(projets)
    assert "wikispecies" in projets


def test_autres_projets_sur_une_ligne_reel():
    assert parse_autres_projets(_article("Escherichia_coli")) == {
        "commons": "Category:Escherichia coli",
        "wikispecies": "Escherichia coli",
        "wiktionary": "Escherichia coli",
    }
    assert parse_autres_projets(_article("Canidae")) == {
        "commons": "Category:Canidae",
        "wikispecies": "Canidae",
    }


def test_autres_projets_alias_du_modele():
    wt = "{{ Autres projets | Commons = A | species = B | Wiktionary2 = C | wikt = D | commons titre = T | commons2 = E }}"
    assert parse_autres_projets(wt) == {
        "commons": "A",
        "wikispecies": "B",
        "wiktionary2": "C",
        "wiktionary": "D",
        "commons2": "E",
    }


def test_autres_projets_premier_argument_positionnel_est_commons():
    assert parse_autres_projets("{{Autres projets|Category:X}}") == {"commons": "Category:X"}


def test_autres_projets_valeur_vide_ou_absent():
    assert parse_autres_projets("{{Autres projets|commons=|wikt=x}}") == {"wiktionary": "x"}
    assert parse_autres_projets("Texte sans modèle") == {}


def test_bases_reelles():
    bases = parse_bases(_article("Lion"))
    assert ("itis", "183803") in bases
    assert ("catalogueoflife", "4CGXP") in bases  # espaces autour du `|`
    assert ("adw", "Panthera_leo") in bases


def test_bases_ignore_les_lignes_sans_modele_en_tete():
    wt = "* Texte {{ITIS|1}}\n* {{Ancre|x}}{{ouvrage|id=Y}}\n* {{ITIS|2|A}}\nhors liste {{NCBI|3}}"
    assert parse_bases(wt) == [("ancre", "x"), ("itis", "2")]


def test_bases_modele_multiligne_et_sans_argument():
    wt = "* {{Tolweb}}\n* {{MSW\n| 14000228\n| ''Panthera leo''\n}}\n* {{ITIS|{{x|1}}|A}}"
    assert parse_bases(wt) == [("tolweb", ""), ("msw", "14000228"), ("itis", "{{x|1}}")]


def test_categorie_principale_sans_argument():
    assert parse_categorie_principale(_article("Mustelidae")) == CategoriePrincipale(None)


def test_categorie_principale_avec_titre():
    assert parse_categorie_principale(_article("Pooideae")) == CategoriePrincipale("Pooideae")
    assert parse_categorie_principale(_article("Myxomycetes")) == CategoriePrincipale("Myxomycetes")


def test_categorie_principale_absente():
    assert parse_categorie_principale(_article("Lion")) is None
    assert parse_categorie_principale(_article("Falconidae")) is None
