"""Normalisation des langues de sources hétérogènes (ISO 639-3, 639-1, nom anglais) vers le code
attendu par {{langue|…}} du Wiktionnaire : ISO 639-1 s'il existe, sinon 639-3."""

from __future__ import annotations

import pytest

from organon.core.langues import LANGUE_INDETERMINEE, code_langue, groupe_par_langue


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        ("fra", "fr"),
        ("fre", "fr"),
        ("fr", "fr"),
        ("FR", "fr"),
        ("French", "fr"),
        ("eng", "en"),
        ("English", "en"),
        ("Spanish", "es"),
        ("zho", "zh"),
        ("haw", "haw"),
        ("Hawaiian", "haw"),
        ("Scottish Gaelic", "gd"),
    ],
)
def test_code_langue_normalise_vers_639_1_sinon_639_3(valeur, attendu):
    assert code_langue(valeur) == attendu


@pytest.mark.parametrize("valeur", [None, "", "  ", "Dothraki", "x"])
def test_code_langue_inconnue_ou_vide_donne_none(valeur):
    assert code_langue(valeur) is None


def test_code_langue_639_3_sans_equivalent_court_est_conserve():
    assert code_langue("ceb") == "ceb"


def test_groupe_par_langue_ordonne_et_deduplique():
    paires = [("fra", "Loup"), ("eng", "Wolf"), ("French", "Loup"), ("fra", "")]

    assert groupe_par_langue(paires) == {"fr": ["Loup"], "en": ["Wolf"]}


def test_groupe_par_langue_conserve_les_noms_sans_code_sous_la_cle_indeterminee():
    paires = [("fra", "Loup"), (None, "Canis"), ("", "Lupo"), ("Dothraki", "Lupo"), ("  ", "Wolf")]

    assert LANGUE_INDETERMINEE == "und"
    assert groupe_par_langue(paires) == {"fr": ["Loup"], "und": ["Canis", "Lupo", "Wolf"]}
