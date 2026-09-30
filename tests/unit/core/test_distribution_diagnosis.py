"""Comparateur de la répartition article/source (pur, sans réseau)."""

from __future__ import annotations

from pathlib import Path

import pytest

from organon.core.config import GenerateOptions
from organon.core.distribution_diagnosis import compare_distribution, diagnose_distribution
from organon.core.distribution_parser import parse_repartition
from organon.core.models import DistributionEntry, Struct, TaxonInfo
from organon.core.rendering.sections import render_distribution

FIX = Path(__file__).parent / "fixtures" / "repartition"


def _entry(certain=(), uncertain=(), introduced=(), extinct=()):
    return DistributionEntry(
        certain={c: c for c in (*certain, *introduced)},
        uncertain={c: c for c in (*uncertain, *extinct)},
        introduced={c: c for c in introduced},
        extinct={c: c for c in extinct},
    )


def _gabarit(**par_statut):
    args = "|".join(f"{k}={','.join(v)}" for k, v in par_statut.items())
    return parse_repartition(f"== Répartition ==\n{{{{WGSRPD|{args}}}}}\ntexte\n")


def _prose(texte):
    return parse_repartition(f"== Répartition ==\n{texte}\n")


# --- niveau 1 : gabarit WGSRPD ---------------------------------------------------------------


def test_niveau1_identique_zero_ecart():
    d = compare_distribution(
        _gabarit(certain=["FRA", "ITA"], introduit=["ABT"]),
        {"powo": _entry(certain=["FRA", "ITA"], introduced=["ABT"])},
    )
    assert d.ecarts == [] and d.niveau == "wgsrpd"


def test_niveau1_code_absent_de_l_article_avertissement():
    d = compare_distribution(
        _gabarit(certain=["FRA"]), {"powo": _entry(certain=["FRA", "ITA", "ESP"])}
    )
    (e,) = d.ecarts
    assert (e.type, e.severite, e.source) == (
        "repartition_code_absent_article", "avertissement", "powo"
    )
    assert e.valeur_source == "ESP, ITA" and e.valeur_wikidata is None
    assert d.comptes is not None and d.comptes.absents_article == ["ESP", "ITA"]


def test_niveau1_statut_different_avertissement():
    d = compare_distribution(
        _gabarit(certain=["FRA", "ITA"]), {"powo": _entry(certain=["FRA"], introduced=["ITA"])}
    )
    (e,) = d.ecarts
    assert (e.type, e.severite) == ("repartition_statut_different", "avertissement")
    assert e.valeur_wikidata == "ITA : certain" and e.valeur_source == "ITA : introduit"


def test_niveau1_incertain_et_eteint_distingues_de_certain():
    d = compare_distribution(
        _gabarit(certain=["A"], incertain=["B"], eteint=["C"]),
        {"powo": _entry(certain=["A"], uncertain=["B"], extinct=["C"])},
    )
    assert d.ecarts == []


def test_niveau1_code_seulement_dans_l_article_jamais_signale():
    d = compare_distribution(
        _gabarit(certain=["FRA", "ITA", "ESP"]), {"powo": _entry(certain=["FRA"])}
    )
    assert d.ecarts == []


def test_niveau1_sans_section_de_repartition():
    v = parse_repartition("== Histoire ==\n{{WGSRPD|certain=CHN}}\n")
    d = compare_distribution(v, {"powo": _entry(certain=["CHN", "CHS"])})
    assert [e.type for e in d.ecarts] == ["repartition_code_absent_article"]


def test_gabarit_avec_source_non_powo_non_compare_limite_exposee():
    d = compare_distribution(_gabarit(certain=["FRA"]), {"col": _entry(certain=["FR", "IT"])})
    assert not any(e.type.startswith("repartition_code") for e in d.ecarts)
    assert any("WGSRPD" in lim for lim in d.limites)


# --- niveau 2 : prose ------------------------------------------------------------------------


def test_niveau2_pays_cite_par_cible_ou_libelle():
    d = compare_distribution(
        _prose("En [[Côte d'Ivoire]], au [[Brésil]] et en [[Allemagne|RFA]]."),
        {"col": _entry(certain=["CI", "BR", "DE"])},
    )
    assert d.ecarts == [] and d.niveau == "prose"


def test_niveau2_insensible_casse_et_accents():
    d = compare_distribution(
        _prose("dans les etats-unis et au bresil"), {"col": _entry(certain=["US", "BR"])}
    )
    assert d.ecarts == []


def test_niveau2_pays_non_cite_info_seulement():
    d = compare_distribution(
        _prose("En [[France]] et au [[Brésil]]."),
        {"col": _entry(certain=["FR", "BR", "PE", "CL"])},
    )
    (e,) = d.ecarts
    assert (e.type, e.severite, e.source) == ("repartition_pays_non_cite", "info", "col")
    assert "Pérou" in e.valeur_source and "Chili" in e.valeur_source
    assert "région" in e.message and "toute l'Europe" in e.message
    assert d.comptes is not None
    assert (d.comptes.n_source, len(d.comptes.absents_article)) == (4, 2)


def test_niveau2_mot_entier_uniquement():
    d = compare_distribution(_prose("Au Nigeria."), {"col": _entry(certain=["NE"])})
    assert [e.type for e in d.ecarts] == ["repartition_pays_non_cite"]


def test_niveau2_texte_seulement_dans_l_article_jamais_signale():
    d = compare_distribution(
        _prose("[[France]], [[Italie]], [[Espagne]], toute l'Europe."),
        {"col": _entry(certain=["FR"])},
    )
    assert d.ecarts == []


def test_niveau2_tous_statuts_comptent():
    d = compare_distribution(
        _prose("En France."),
        {"col": _entry(certain=["FR"], uncertain=["IT"], introduced=["ES"], extinct=["PT"])},
    )
    assert d.comptes is not None and d.comptes.n_source == 4
    assert len(d.comptes.absents_article) == 3


def test_niveau2_code_inconnu_ignore_et_signale():
    d = compare_distribution(_prose("En France."), {"col": _entry(certain=["FR", "ZZZ9"])})
    assert d.ecarts == [] and any("ZZZ9" in lim for lim in d.limites)


def test_niveau2_powo_sans_gabarit_utilise_les_noms_wgsrpd():
    d = compare_distribution(
        _prose("Présente en [[Italie]]."), {"powo": _entry(certain=["ITA", "FRA"])}
    )
    (e,) = d.ecarts
    assert e.type == "repartition_pays_non_cite" and "France" in e.valeur_source


# --- limites et cas neutres ------------------------------------------------------------------


def test_section_non_identifiee_limite_et_info_si_source_a_des_donnees():
    d = compare_distribution(
        parse_repartition("== Description ==\nx\n"), {"col": _entry(certain=["FR"])}
    )
    assert [(e.type, e.severite) for e in d.ecarts] == [("section_repartition_absente", "info")]
    assert d.comptes is None and len(d.limites) == 1


def test_section_non_identifiee_source_muette_rien():
    d = compare_distribution(parse_repartition("x"), {"col": _entry()})
    assert d.ecarts == [] and d.limites == []


def test_source_absente_ou_vide_jamais_un_ecart():
    assert compare_distribution(_prose("En France."), {}).ecarts == []
    assert compare_distribution(_gabarit(certain=["FRA"]), {"powo": _entry()}).ecarts == []


def test_plusieurs_sources_non_comparees():
    d = compare_distribution(
        _prose("x"), {"col": _entry(certain=["FR"]), "powo": _entry(certain=["ITA"])}
    )
    assert d.ecarts == [] and len(d.limites) == 1


def test_diagnose_retourne_les_ecarts():
    assert diagnose_distribution(_prose("En France."), {"col": _entry(certain=["FR", "IT"])})


# --- aller-retour avec le générateur ---------------------------------------------------------


def _rendu(source, entry):
    struct = Struct(
        taxon=TaxonInfo(name="Genus species", rank="espèce"),
        kingdom="vegetal",
        distribution={source: entry},
    )
    return render_distribution(struct, GenerateOptions())


@pytest.mark.parametrize("n", [3, 40])
def test_aller_retour_powo_zero_ecart(n):
    codes = ["FRA", "ITA", "ESP", "GER", "BGM", "NET", "SWI", "AUT", "POL", "CZE"]
    if n == 40:
        codes += [f"X{i:02d}" for i in range(30)]
    entry = _entry(certain=codes[:-2], uncertain=codes[-2:-1], introduced=codes[-1:])
    vue = parse_repartition(_rendu("powo", entry))
    assert vue.wgsrpd is not None and vue.section_identifiee
    assert compare_distribution(vue, {"powo": entry}).ecarts == []


@pytest.mark.parametrize(
    "codes",
    [["FR", "IT"], ["FR", "IT", "ES", "DE", "BE", "NL", "CH", "AT", "PL", "CZ", "PT", "IE"]],
)
def test_aller_retour_non_powo_zero_ecart(codes):
    entry = _entry(certain=codes[:-1], introduced=codes[-1:])
    vue = parse_repartition(_rendu("col", entry))
    d = compare_distribution(vue, {"col": entry})
    assert d.ecarts == [] and d.niveau == "prose"


# --- articles réels figés --------------------------------------------------------------------


def _fix(nom):
    return parse_repartition((FIX / f"{nom}.wiki").read_text(encoding="utf-8"))


def test_reel_metaxya_niveau1_source_identique():
    v = _fix("Metaxya")
    src = _entry(certain=sorted(v.wgsrpd["certain"]), uncertain=sorted(v.wgsrpd["incertain"]))
    assert compare_distribution(v, {"powo": src}).ecarts == []


def test_reel_metaxya_code_supplementaire_de_la_source_signale():
    v = _fix("Metaxya")
    src = _entry(certain=[*sorted(v.wgsrpd["certain"]), "FRA"])
    assert [e.type for e in compare_distribution(v, {"powo": src}).ecarts] == [
        "repartition_code_absent_article"
    ]


def test_reel_rosa_canina_prose_pays_cites():
    d = compare_distribution(
        _fix("Rosa_canina"),
        {"col": _entry(certain=["AF", "IR", "IQ", "LB", "SY", "TJ", "PK", "FR"])},
    )
    assert [e.type for e in d.ecarts] == ["repartition_pays_non_cite"]  # France : « toute l'Europe »
    assert d.ecarts[0].valeur_source == "France"


def test_reel_lion_sous_sections_lues():
    d = compare_distribution(_fix("Lion"), {"col": _entry(certain=["IN", "KE"])})
    assert d.niveau == "prose" and d.comptes is not None


def test_reel_sans_section():
    d = compare_distribution(_fix("Tyrannosaurus"), {"col": _entry(certain=["US"])})
    assert [e.type for e in d.ecarts] == ["section_repartition_absente"]
