"""Comparateur Taxobox article ↔ rangs de la source (pur, sans réseau)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, TaxonInfo
from organon.core.rendering.sections import compute_rank_lines, render_taxobox
from organon.core.taxobox_diagnosis import diagnose_taxobox, diagnose_uicn
from organon.core.taxobox_parser import (
    TaxoboxRang,
    TaxoboxTaxon,
    TaxoboxUicn,
    TaxoboxView,
    parse_taxobox,
)

RANGS = [("famille", "Felidae"), ("genre", "Panthera")]


def _view(rangs=None, taxon=None, classification="msw") -> TaxoboxView:
    return TaxoboxView(
        classification,
        taxon or TaxoboxTaxon("animal", "espèce", "Panthera leo", False),
        rangs if rangs is not None else [TaxoboxRang(r, n, False) for r, n in RANGS],
    )


def _diag(view, **kw):
    args = {
        "rank_lines": RANGS,
        "taxon_nom": "Panthera leo",
        "taxon_rang": "espèce",
        "source": "msw",
    }
    args.update(kw)
    return diagnose_taxobox(view, **args)


def _types(ecarts):
    return [e.type for e in ecarts]


def test_taxobox_identique_aucun_ecart():
    assert _diag(_view()) == []


def test_taxobox_absente():
    (e,) = _diag(None)
    assert (e.type, e.severite, e.source) == ("taxobox_absente", "avertissement", "msw")


def test_nom_different_meme_rang_casefold_ignore():
    view = _view([TaxoboxRang("famille", "FELIDAE", False), TaxoboxRang("genre", "Leo", False)])
    (e,) = _diag(view)
    assert (e.type, e.severite, e.propriete) == ("taxobox_nom_different", "erreur", "genre")
    assert (e.valeur_wikidata, e.valeur_source) == ("Leo", "Panthera")


def test_rang_sans_nom_ignore_pour_la_comparaison():
    view = _view([TaxoboxRang("famille", None, False), TaxoboxRang("genre", "Panthera", False)])
    assert _diag(view) == []


def test_rang_absent_article():
    view = _view([TaxoboxRang("genre", "Panthera", False)])
    (e,) = _diag(view)
    assert (e.type, e.severite, e.propriete) == ("taxobox_rang_absent_article", "info", "famille")
    assert (e.valeur_wikidata, e.valeur_source) == (None, "Felidae")


def test_rang_absent_source():
    view = _view([*_view().rangs, TaxoboxRang("ordre", "Carnivora", False)])
    (e,) = _diag(view)
    assert (e.type, e.severite, e.propriete) == ("taxobox_rang_absent_source", "info", "ordre")
    assert (e.valeur_wikidata, e.valeur_source) == ("Carnivora", None)


def test_taxon_nom_different():
    (e,) = _diag(_view(taxon=TaxoboxTaxon("animal", "espèce", "Panthera pardus", False)))
    assert (e.type, e.severite) == ("taxobox_taxon_different", "erreur")
    assert (e.valeur_wikidata, e.valeur_source) == ("Panthera pardus", "Panthera leo")


def test_taxon_rang_different():
    (e,) = _diag(_view(taxon=TaxoboxTaxon("animal", "genre", "Panthera leo", False)))
    assert (e.type, e.severite) == ("taxobox_taxon_different", "erreur")
    assert (e.valeur_wikidata, e.valeur_source) == ("genre", "espèce")


def test_synonyme_suivi_un_seul_ecart_de_nom_et_arret():
    view = _view(
        [TaxoboxRang("famille", "X", False)],
        taxon=TaxoboxTaxon("animal", "genre", "Felis leo", False),
    )
    ecarts = _diag(view, redirected_from="Felis leo")
    assert _types(ecarts) == ["taxobox_taxon_different"]
    assert "Felis leo" in ecarts[0].message


def test_classification_differente_info():
    (e,) = _diag(_view(classification="COL"))
    assert (e.type, e.severite) == ("taxobox_classification", "info")
    assert (e.valeur_wikidata, e.valeur_source) == ("COL", "msw")


def test_classification_absente_de_l_article_pas_un_ecart():
    assert _diag(_view(classification=None)) == []


def test_aller_retour_generateur_parseur_zero_ecart():
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo", rank="espèce", author="(Linnaeus, 1758)"),
        classification="msw",
        classification_taxobox="msw",
        kingdom="animal",
        ranks=[
            RankName(name="Panthera", rank="genre"),
            RankName(name="Felidae", rank="famille"),
            RankName(name="Carnivora", rank="ordre"),
            RankName(name="Mammalia", rank="classe"),
            RankName(name="Chordata", rank="embranchement", extinct=False),
        ],
    )
    wikitext = render_taxobox(struct, GenerateOptions(), [])
    view = parse_taxobox(wikitext)
    assert view is not None and len(view.rangs) == 5
    rank_lines = [(rang, nom) for rang, nom, _ in compute_rank_lines(struct)]
    assert (
        diagnose_taxobox(
            view,
            rank_lines=rank_lines,
            taxon_nom="Panthera leo",
            taxon_rang="espèce",
            source=struct.classification_taxobox,
        )
        == []
    )


def _uicn_view(uicn) -> TaxoboxView:
    return TaxoboxView("msw", None, [], uicn)


def _diag_uicn(uicn, risque, critere=None):
    return diagnose_uicn(_uicn_view(uicn), risque=risque, critere=critere, source="iucn")


def test_uicn_identique_aucun_ecart():
    assert _diag_uicn(TaxoboxUicn("VU", "A2c"), "VU", "A2c") == []
    assert _diag_uicn(TaxoboxUicn("LC", None), "LC", None) == []


def test_uicn_code_different():
    ecarts = _diag_uicn(TaxoboxUicn("LC", None), "EN", None)
    assert _types(ecarts) == ["uicn_different"]
    assert ecarts[0].severite == "avertissement"
    assert (ecarts[0].valeur_wikidata, ecarts[0].valeur_source) == ("LC", "EN")


def test_uicn_critere_different():
    ecarts = _diag_uicn(TaxoboxUicn("EN", "A2abcd"), "EN", "B1ab(iii)")
    assert _types(ecarts) == ["uicn_different"]
    assert (ecarts[0].valeur_wikidata, ecarts[0].valeur_source) == (
        "EN A2abcd",
        "EN B1ab(iii)",
    )


def test_uicn_critere_absent_de_la_source_pas_un_ecart():
    assert _diag_uicn(TaxoboxUicn("EN", "A2abcd"), "EN", None) == []


def test_uicn_absent_article_info():
    ecarts = _diag_uicn(None, "VU", "A2c")
    assert _types(ecarts) == ["uicn_absent_article"]
    assert ecarts[0].severite == "info"


def test_uicn_article_seul_non_signale():
    assert _diag_uicn(TaxoboxUicn("LC", None), None, None) == []
    assert diagnose_uicn(None, risque=None, critere=None, source="iucn") == []


def test_uicn_aller_retour_generateur_parseur_zero_ecart():
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo", rank="espèce", author="(Linnaeus, 1758)"),
        classification="msw",
        classification_taxobox="msw",
        kingdom="animal",
        ranks=[RankName(name="Panthera", rank="genre")],
        links={"iucn": {"risk": "VU", "criterion": "A2c"}},
    )
    view = parse_taxobox(render_taxobox(struct, GenerateOptions(), []))
    assert view is not None and view.uicn == TaxoboxUicn("VU", "A2c")
    assert diagnose_uicn(view, risque="VU", critere="A2c", source="iucn") == []
    struct.links["iucn"] = {"risk": "LC"}
    view = parse_taxobox(render_taxobox(struct, GenerateOptions(), []))
    assert view is not None and view.uicn == TaxoboxUicn("LC", None)
    assert diagnose_uicn(view, risque="LC", critere=None, source="iucn") == []
