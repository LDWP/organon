"""Propriétés du parseur de Taxobox : robustesse sur wikitexte arbitraire et aller-retour sur
des taxobox générées."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from organon.core.taxobox_parser import TaxoboxRang, TaxoboxView, parse_taxobox

settings.register_profile(
    "organon",
    max_examples=100,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("organon")

# Alphabet pondéré vers la syntaxe wiki pour atteindre les branches de découpage.
_FRAGMENTS = st.sampled_from(
    ["{{", "}}", "[[", "]]", "|", "=", "'", "<!--", "-->", "\n", " ", "éteint", "oui",
     "Taxobox début", "Taxobox fin", "Taxobox", "Taxobox taxon", "Taxobox UICN",
     "classification", "animal", "espèce", "genre", "Panthera", "leo"]
)
_WIKITEXT = st.one_of(st.text(), st.lists(_FRAGMENTS, max_size=40).map("".join))

# Noms sans syntaxe wiki ni espaces en bordure (le parseur les `strip`).
_NOM = st.from_regex(r"[A-Za-z][A-Za-z ]{0,18}[A-Za-z]", fullmatch=True)
_RANG = st.sampled_from(["classe", "ordre", "famille", "genre", "sous-ordre"])


@given(_WIKITEXT)
def test_ne_leve_jamais_sur_du_wikitexte_arbitraire(texte):
    view = parse_taxobox(texte)
    assert view is None or isinstance(view, TaxoboxView)


@given(_WIKITEXT)
def test_sans_taxobox_debut_le_resultat_est_none(texte):
    if "taxobox début" not in texte.casefold():
        assert parse_taxobox(texte) is None


@given(_WIKITEXT)
def test_parse_est_deterministe(texte):
    assert parse_taxobox(texte) == parse_taxobox(texte)


@given(st.lists(st.tuples(_RANG, _NOM, st.booleans()), max_size=8), st.one_of(st.none(), _NOM))
def test_aller_retour_des_rangs_et_de_la_classification(rangs, classification):
    lignes = [
        "{{Taxobox début | animal | Titre"
        + (f" | classification={classification}" if classification else "")
        + " }}"
    ]
    for rang, nom, eteint in rangs:
        suffixe = " | éteint=oui" if eteint else ""
        lignes.append(f"{{{{Taxobox | {rang} | [[{nom}]]{suffixe}}}}}")
    lignes.append("{{Taxobox fin}}")

    view = parse_taxobox("\n".join(lignes))

    assert view is not None
    assert view.classification == classification
    assert view.rangs == [TaxoboxRang(r, n, e) for r, n, e in rangs]


@given(_RANG)
def test_rang_sans_nom_exploitable_donne_none(rang):
    view = parse_taxobox(f"{{{{Taxobox début}}}}{{{{Taxobox | {rang} }}}}{{{{Taxobox fin}}}}")
    assert view is not None
    assert view.rangs == [TaxoboxRang(rang, None, False)]


@given(_NOM)
def test_valeurs_absentes_donnent_none(nom):
    view = parse_taxobox(f"{{{{Taxobox début}}}}{{{{Taxobox | genre | {nom} }}}}")
    assert view is not None
    assert view.classification is None
    assert view.taxon is None
    assert view.uicn is None
