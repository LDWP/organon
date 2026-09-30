"""Parseur de la Taxobox d'un article frwiki. Fixtures = wikitexte réel figé (fr.wikipedia.org,
action=raw, 2026-09-24) : bloc `{{Taxobox début}}` … `{{Taxobox fin}}` de chaque article."""

from __future__ import annotations

from pathlib import Path

from organon.core.taxobox_parser import TaxoboxRang, TaxoboxTaxon, TaxoboxUicn, parse_taxobox

FIXTURES = Path(__file__).parent / "fixtures" / "taxobox"


def _fixture(nom: str) -> str:
    return (FIXTURES / f"{nom}.txt").read_text(encoding="utf-8")


def _rangs(nom: str) -> list[tuple[str, str | None]]:
    view = parse_taxobox(_fixture(nom))
    assert view is not None
    return [(r.rang, r.nom) for r in view.rangs]


def test_lion_rangs_du_plus_haut_au_plus_bas_et_taxon():
    view = parse_taxobox(_fixture("Lion"))
    assert view is not None
    assert _rangs("Lion") == [
        ("embranchement", "Chordata"),
        ("sous-embranchement", "Vertebrata"),
        ("classe", "Mammalia"),
        ("ordre", "Carnivora"),
        ("sous-ordre", "Feliformia"),
        ("famille", "Felidae"),
        ("sous-famille", "Pantherinae"),
        ("genre", "Panthera"),
    ]
    assert view.taxon == TaxoboxTaxon("animal", "espèce", "Panthera leo", False)
    assert view.classification == "msw"


def test_lion_ignore_plage_repartition_uicn_cites_et_synonymes():
    # les blocs imbriqués ({{Liste cachée|…}}) de `Taxobox synonymes` ne fuient pas
    assert len(_rangs("Lion")) == 8


def test_falconidae_ignore_le_bloc_taxons_multiligne():
    assert _rangs("Falconidae") == [
        ("embranchement", "Chordata"),
        ("sous-embranchement", "Vertebrata"),
        ("classe", "Aves"),
        ("ordre", "Falconiformes"),
    ]
    view = parse_taxobox(_fixture("Falconidae"))
    assert view is not None and view.taxon == TaxoboxTaxon("animal", "famille", "Falconidae", False)
    assert view.classification == "COI"


def test_escherichia_coli_nom_du_taxon_dépouillé_des_italiques():
    view = parse_taxobox(_fixture("Escherichia_coli"))
    assert view is not None
    assert view.taxon == TaxoboxTaxon("bactérie", "espèce", "Escherichia coli", False)
    assert view.classification == "LPSN"  # `classification = LPSN` : espaces autour du `=`


def test_espaces_et_tabulations_variables_et_nom_vernaculaire_puis_latin():
    rangs = _rangs("Rosaceae")
    assert ("sous-division", "Spermatophytina") in rangs  # `{{Taxobox |sous-division|X }}`
    assert ("classe", "Magnoliopsida") in rangs  # `classe | Angiosperme |\tMagnoliopsida`


def test_vernaculaire_puis_latin_sur_un_bloc_dont_fin_partage_la_ligne():
    # `{{Taxobox fin}}` collé à la fin d'un bloc multiligne (Nyctereutes)
    assert _rangs("Nyctereutes")[:3] == [
        ("embranchement", "Chordata"),
        ("sous-embranchement", "Vertebrata"),
        ("classe", "Mammalia"),
    ]
    view = parse_taxobox(_fixture("Nyctereutes"))
    assert view is not None and view.taxon is not None
    assert view.taxon.nom == "Nyctereutes procyonoides"


def test_eteint_nomme_ne_devient_pas_le_nom():
    view = parse_taxobox(_fixture("Tyrannosaurus"))
    assert view is not None
    assert TaxoboxRang("sous-famille", "Tyrannosaurinae", True) in view.rangs
    assert TaxoboxRang("classe", "Sauropsida", False) in view.rangs
    assert view.taxon == TaxoboxTaxon("animal", "genre", "Tyrannosaurus", True)


def test_page_d_homonymie_non_resolue_donne_un_nom_absent():
    # sortie de `compute_rank_lines` quand la table d'homonymes renvoie une page d'homonymie
    wikitext = (
        "{{Taxobox début | animal | Foo | | | classification=COI }}\n"
        "{{Taxobox | genre | {{Lien vers une page d'homonymie|Foo}} }}\n"
        "{{Taxobox taxon | animal | espèce | Foo bar | Auteur }}\n"
        "{{Taxobox fin}}"
    )
    view = parse_taxobox(wikitext)
    assert view is not None
    assert view.rangs == [TaxoboxRang("genre", None, False)]


def test_lien_wiki_et_italiques_dans_le_nom():
    wikitext = (
        "{{Taxobox début | animal | Foo | | }}\n"
        "{{Taxobox | genre | [[Foo (genre)|''Foo'']] }}\n"
        "{{Taxobox taxon | animal | genre | '''''Foo''''' | Auteur }}\n"
        "{{Taxobox fin}}"
    )
    view = parse_taxobox(wikitext)
    assert view is not None
    assert view.rangs == [TaxoboxRang("genre", "Foo", False)]
    assert view.taxon is not None and view.taxon.nom == "Foo"


def test_commentaire_html_ignoré():
    wikitext = (
        "{{Taxobox début | animal | Foo | | }}\n"
        "<!-- {{Taxobox | ordre | Fantôme }} -->\n"
        "{{Taxobox | ordre | Réel }}\n"
        "{{Taxobox fin}}"
    )
    view = parse_taxobox(wikitext)
    assert view is not None and view.rangs == [TaxoboxRang("ordre", "Réel", False)]


def test_taxobox_dans_un_article_entier_et_sans_taxobox():
    article = "Intro.\n" + _fixture("Falconidae") + "\n== Suite ==\n{{Taxobox | ordre | Piège }}"
    view = parse_taxobox(article)
    assert view is not None and ("ordre", "Piège") not in [(r.rang, r.nom) for r in view.rangs]
    assert parse_taxobox("Article sans taxobox.\n{{Portail|biologie}}") is None


def test_taxobox_sans_ligne_taxon():
    view = parse_taxobox("{{Taxobox début | animal | Foo | | }}\n{{Taxobox fin}}")
    assert view is not None and view.taxon is None and view.rangs == []


def _uicn(nom: str):
    view = parse_taxobox(_fixture(nom))
    assert view is not None
    return view.uicn


def test_uicn_avec_critere():
    assert _uicn("Tigre_uicn") == TaxoboxUicn("EN", "A2abcd")
    assert _uicn("Lion") == TaxoboxUicn("VU", "A2c")


def test_uicn_critere_complexe():
    assert _uicn("Panda_geant_uicn") == TaxoboxUicn("VU", "C2a(i);D1")


def test_uicn_sans_critere():
    assert _uicn("Homo_sapiens_uicn") == TaxoboxUicn("LC", None)


def test_uicn_commentaire_html_ignore():
    assert _uicn("Rhinoceros_blanc_uicn") == TaxoboxUicn("NT", None)


def test_uicn_absente():
    assert _uicn("Rosaceae") is None
