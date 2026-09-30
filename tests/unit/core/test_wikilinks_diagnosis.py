"""Comparateur des liens externes article ↔ sortie du générateur (pur, sans réseau)."""

from __future__ import annotations

from pathlib import Path

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.core.registry import _REGISTRY
from organon.core.rendering.sections import render_see_also
from organon.core.wikilinks_diagnosis import diagnose_liens
from organon.modules.itis.module import ItisModule
from organon.modules.ncbi.module import NcbiModule

FIXTURES = Path(__file__).parent / "fixtures" / "wikilinks"

ATTENDU = (
    "\n== Liens externes ==\n"
    "{{Autres projets\n| commons=Category:Canidae\n| wikispecies=Canidae\n}}\n"
    "{{catégorie principale}}\n"
    "* {{ITIS | 180594 | Canidae | consulté le=1 janvier 2026 }}\n"
    "* {{NCBI | 9608 | Canidae | consulté le=1 janvier 2026 }}\n"
)


def _diag(article: str, attendu: str = ATTENDU):
    return diagnose_liens(article, attendu, source="itis")


def _types(ecarts):
    return [e.type for e in ecarts]


def test_article_conforme_zero_ecart():
    article = (
        "== Liens externes ==\n{{Autres projets|commons=Category:Canidae|species=Canidae}}\n"
        "{{Catégorie principale}}\n* {{ITIS|180594|''Canidae''|consulté le=2014}}\n"
        "* {{NCBI|9608|''Canidae''}}\n"
    )
    assert _diag(article) == []


def test_projet_absent_article_info():
    article = (
        "{{Autres projets|commons=Category:Canidae}}\n{{catégorie principale}}\n"
        "* {{ITIS|180594}}\n* {{NCBI|9608}}\n"
    )
    ecarts = _diag(article)
    assert _types(ecarts) == ["projet_absent_article"]
    assert ecarts[0].severite == "info"
    assert ecarts[0].valeur_source == "Canidae"
    assert ecarts[0].valeur_wikidata is None


def test_projet_different_avertissement():
    article = (
        "{{Autres projets|commons=Category:Canidae|wikispecies=Canis}}\n{{catégorie principale}}\n"
        "* {{ITIS|180594}}\n* {{NCBI|9608}}\n"
    )
    ecarts = _diag(article)
    assert _types(ecarts) == ["projet_different"]
    assert ecarts[0].severite == "avertissement"
    assert (ecarts[0].valeur_wikidata, ecarts[0].valeur_source) == ("Canis", "Canidae")


def test_alias_et_underscores_equivalents():
    article = (
        "{{Autres projets|Commons=Category:Canidae|wikispecies=Canidae}}\n{{catégorie principale}}\n"
        "* {{ITIS|180594}}\n* {{NCBI|9608}}\n"
    )
    assert _diag(article) == []
    article = article.replace("Category:Canidae", "Category:Canidae_x")
    attendu = ATTENDU.replace("Category:Canidae", "Category:Canidae x")
    assert _diag(article, attendu) == []


def test_categorie_principale_absente_info():
    article = (
        "{{Autres projets|commons=Category:Canidae|species=Canidae}}\n"
        "* {{ITIS|180594}}\n* {{NCBI|9608}}\n"
    )
    ecarts = _diag(article)
    assert _types(ecarts) == ["categorie_principale_absente"]
    assert ecarts[0].severite == "info"


def test_categorie_principale_avec_titre_en_article_pas_un_ecart():
    article = (
        "{{Autres projets|commons=Category:Canidae|species=Canidae}}\n"
        "{{Catégorie principale|Canidae (famille)}}\n* {{ITIS|180594}}\n* {{NCBI|9608}}\n"
    )
    assert _diag(article) == []


def test_base_absente_article_info():
    article = (
        "{{Autres projets|commons=Category:Canidae|species=Canidae}}\n{{catégorie principale}}\n"
        "* {{ITIS|180594}}\n"
    )
    ecarts = _diag(article)
    assert _types(ecarts) == ["base_absente_article"]
    assert ecarts[0].severite == "info"
    assert ecarts[0].propriete == "NCBI"


def test_base_identifiant_different_avertissement():
    article = (
        "{{Autres projets|commons=Category:Canidae|species=Canidae}}\n{{catégorie principale}}\n"
        "* {{ITIS|999}}\n* {{NCBI|9608}}\n"
    )
    ecarts = _diag(article)
    assert _types(ecarts) == ["base_identifiant_different"]
    assert ecarts[0].severite == "avertissement"
    assert (ecarts[0].valeur_wikidata, ecarts[0].valeur_source) == ("999", "180594")


def test_base_seulement_dans_l_article_non_signalee_et_hors_liste_ignore():
    article = (
        "{{Autres projets|commons=Category:Canidae|species=Canidae}}\n{{catégorie principale}}\n"
        "* {{ITIS|180594}}\n* {{NCBI|9608}}\n* {{MSW|14000691|Canidae}}\n"
        "* {{lien web|url=http://x|titre=Y}}\n* {{ouvrage|id=Z}}\n{{Palette Carnivora}}\n"
    )
    assert _diag(article) == []


def test_lien_web_attendu_non_compare():
    attendu = ATTENDU + "* {{Lien web | langue=en | titre=X | url=http://a }}\n"
    article = (
        "{{Autres projets|commons=Category:Canidae|species=Canidae}}\n{{catégorie principale}}\n"
        "* {{ITIS|180594}}\n* {{NCBI|9608}}\n"
    )
    assert _diag(article, attendu) == []


def test_article_reel_falconidae():
    article = (FIXTURES / "Falconidae.wiki").read_text(encoding="utf-8")
    attendu = (
        "\n== Liens externes ==\n{{Autres projets\n| commons=Category:Falconidae\n"
        "| species=Falconidae\n}}\n{{catégorie principale}}\n"
        "* {{ITIS | 1 | Falconidae | consulté le=x }}\n"
        "* {{NCBI | 8949 | Falconidae | consulté le=x }}\n"
        "* {{TPDB | 39999 | Falconidae | consulté le=x }}\n"
        "* {{Tolweb | Falconidae | consulté le=x }}\n"
    )
    assert [(e.type, e.propriete) for e in _diag(article, attendu)] == [
        ("projet_absent_article", "Autres projets"),
        ("categorie_principale_absente", "catégorie principale"),
        ("base_absente_article", "ITIS"),
        ("base_identifiant_different", "TPDB"),
    ]


def test_article_reel_lion_commons_categorie_pas_un_faux_positif():
    article = (FIXTURES / "Lion.wiki").read_text(encoding="utf-8")
    attendu = (
        "\n== Liens externes ==\n{{Autres projets\n| commons=Panthera leo\n"
        "| commons2=Category:Panthera leo\n| commons titre2=Catégorie Panthera leo\n"
        "| species=Panthera leo\n| wiktionary=lion\n}}\n"
    )
    ecarts = _diag(article, attendu)
    assert [(e.type, e.propriete, e.valeur_source) for e in ecarts] == [
        ("projet_absent_article", "Autres projets", "Panthera leo")
    ]
    assert ecarts[0].severite == "info"


def test_commons_different_de_toute_valeur_de_la_source_reste_un_avertissement():
    article = "{{Autres projets|commons=Category:Autre}}"
    attendu = "{{Autres projets|commons=Canidae|commons2=Category:Canidae}}"
    types = [e.type for e in _diag(article, attendu)]
    assert types == ["projet_different", "projet_absent_article"]


def test_attendu_vide_zero_ecart():
    assert _diag("{{Autres projets|commons=X}}", "") == []


def test_aller_retour_generateur_parseur_zero_ecart(monkeypatch):
    monkeypatch.setitem(_REGISTRY, "itis", ItisModule())
    monkeypatch.setitem(_REGISTRY, "ncbi", NcbiModule())
    struct = Struct(
        taxon=TaxonInfo(name="Canidae", rank="famille"),
        kingdom="animal",
        links={
            "wikimedia": {
                "commons": {"page": "Canidae"},
                "commons_category": {"page": "Canidae"},
                "wikispecies": {"page": "Canidae"},
                "frwiktionary": {"page": "canidé"},
            },
            "itis": {"id": 180594, "name": "Canidae"},
            "ncbi": {"id": 9608, "name": "Canidae"},
        },
    )
    rendu = render_see_also(struct, GenerateOptions())
    assert "{{Autres projets" in rendu and "{{ITIS" in rendu and "{{catégorie principale}}" in rendu
    assert diagnose_liens(rendu, rendu, source="itis") == []
