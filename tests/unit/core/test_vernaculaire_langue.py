"""Struct.vernacular porte la langue de chaque nom (module -> code ISO -> noms) ; le rendu
Wikipédia et le résumé API n'utilisent que le français."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.core.rendering.sections import render_systematics


def _struct() -> Struct:
    struct = Struct(taxon=TaxonInfo(name="Canis lupus"))
    struct.vernacular["ITIS"] = {"fr": ["Loup gris"], "en": ["Gray wolf"]}
    struct.vernacular["GBIF"] = {"en": ["Gray wolf"]}
    return struct


def test_noms_vernaculaires_filtre_par_langue_et_omet_les_modules_sans_nom():
    struct = _struct()

    assert struct.vernacular_names("fr") == {"ITIS": ["Loup gris"]}
    assert struct.vernacular_names("en") == {"ITIS": ["Gray wolf"], "GBIF": ["Gray wolf"]}


def test_rendu_wikipedia_ne_garde_que_le_francais():
    texte = render_systematics(_struct(), GenerateOptions())

    assert "Loup gris" in texte
    assert "Gray wolf" not in texte


def test_rendu_wikipedia_sans_nom_francais_n_ecrit_pas_la_phrase():
    struct = Struct(taxon=TaxonInfo(name="Canis lupus"))
    struct.vernacular["GBIF"] = {"en": ["Gray wolf"]}

    assert "Ce taxon porte en français" not in render_systematics(struct, GenerateOptions())


def test_noms_sans_code_langue_ne_sont_pas_rendus_sur_wikipedia():
    struct = Struct(taxon=TaxonInfo(name="Canis lupus"))
    struct.vernacular["GBIF"] = {"und": ["Canis"], "fr": ["Loup gris"]}

    texte = render_systematics(struct, GenerateOptions())

    assert "Loup gris" in texte
    assert "Canis" not in texte.replace("Canis lupus", "")
    assert struct.vernacular_names("fr") == {"GBIF": ["Loup gris"]}
