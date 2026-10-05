"""Auteurs botaniques absents du yaml : lien {{Lien}} vers Wikidata si l'entité existe."""

from organon.core.models import Struct, TaxonInfo
from organon.core.rendering.authors import resolve_main_author, unknown_botanist_tokens


def _plant(author: str, kingdom: str = "végétal") -> Struct:
    return Struct(
        taxon=TaxonInfo(name="Blasiaceae", rank="famille", author=author), kingdom=kingdom
    )


def test_unknown_botanist_tokens_skips_known_authors_and_years():
    # « A.Arber » est dans le yaml, « H. Klinggr. » non.
    assert unknown_botanist_tokens(_plant("H. Klinggr., A.Arber, 1753")) == ["H. Klinggr."]


def test_unknown_botanist_tokens_empty_outside_botanical_kingdoms():
    assert unknown_botanist_tokens(_plant("H. Klinggr.", kingdom="animal")) == []


def test_unresolved_botanist_falls_back_to_auteur_template():
    text, _ = resolve_main_author(_plant("H. Klinggr."))
    assert text == "{{auteur|[[H. Klinggr.]]}} {{date à préciser}}"


def test_wikidata_entity_renders_lien_template():
    text, _ = resolve_main_author(_plant("H. Klinggr."), {"H.Klinggr.": "Q5933938"})
    assert (
        text == "{{Lien|langue=d|trad=Q5933938|texte=H. Klinggr.|lienfr=non}} {{date à préciser}}"
    )


def test_yaml_entry_wins_over_wikidata():
    text, _ = resolve_main_author(_plant("A.Arber"), {"A.Arber": "Q1"})
    assert "Q1" not in text
