"""Comparateur pur Wikidata <-> source Organon : un test par type d'écart, plus les cas où une
donnée manquante d'un côté ne doit jamais devenir une erreur."""

from __future__ import annotations

from datetime import date

from organon.core.update_diagnosis import (
    ContextePropositions,
    IdentifiantWikidata,
    SourceView,
    StatementSansReference,
    WikidataView,
    diagnose,
)


def _wd(**kw) -> WikidataView:
    base = dict(
        qid="Q140",
        is_taxon=True,
        names=["Panthera leo"],
        rank="espèce",
        parent_names=["Panthera"],
        synonyms=[],
        external_ids={},
        unreferenced=[],
    )
    return WikidataView(**{**base, **kw})


def _src(**kw) -> SourceView:
    base = dict(
        source="col",
        name="Panthera leo",
        rank="espèce",
        parent_name="Panthera",
        synonyms=[],
        external_ids={},
        redirected_from=None,
    )
    return SourceView(**{**base, **kw})


def _ctx(**kw) -> ContextePropositions:
    base = dict(
        retrieved=date(2026, 9, 24),
        database_items={"col": "Q38840", "itis": "Q82575", "gbif": "Q1531570"},
        rank_qid="Q7432",
        resolved_items={},
        id_properties={
            "itis": IdentifiantWikidata(propriete="P815"),
            "powo": IdentifiantWikidata(propriete="P5037", prefixe="urn:lsid:ipni.org:names:"),
        },
    )
    return ContextePropositions(**{**base, **kw})


def _types(ecarts):
    return sorted(e.type for e in ecarts)


def test_no_gap_when_everything_matches():
    assert diagnose(_wd(), _src()) == []


def test_every_gap_names_its_source():
    ecarts = diagnose(_wd(rank="genre"), _src(source="gbif"))
    assert ecarts and all(e.source == "gbif" for e in ecarts)


def test_item_not_a_taxon_is_error():
    (e,) = diagnose(_wd(is_taxon=False), _src())
    assert (e.type, e.severite) == ("item_non_taxon", "erreur")


def test_name_mismatch_is_error():
    (e,) = diagnose(_wd(names=["Felis leo"]), _src())
    assert (e.type, e.severite, e.valeur_wikidata, e.valeur_source) == (
        "nom_different",
        "erreur",
        "Felis leo",
        "Panthera leo",
    )


def test_name_matches_any_p225_value():
    assert diagnose(_wd(names=["Felis leo", "Panthera leo"]), _src()) == []


def test_redirection_reports_name_only_and_skips_other_comparisons():
    wd = _wd(names=["Felis leo"], rank="genre", external_ids={"col": ["OLD"]})
    src = _src(redirected_from="Felis leo", external_ids={"col": "NEW"})
    (e,) = diagnose(wd, src)
    assert e.type == "nom_synonyme_source"
    assert e.severite == "erreur"


def test_rank_mismatch_is_error():
    (e,) = diagnose(_wd(rank="genre"), _src())
    assert (e.type, e.severite) == ("rang_different", "erreur")


def test_silent_source_is_never_a_gap():
    assert diagnose(_wd(), _src(rank=None, parent_name=None)) == []


def test_missing_rank_or_parent_without_target_is_info_without_proposal():
    ecarts = diagnose(_wd(rank=None, parent_names=[]), _src())
    assert _types(ecarts) == ["parent_absent_wikidata", "rang_absent_wikidata"]
    assert {e.severite for e in ecarts} == {"info"}
    assert {e.proposition for e in ecarts} == {None}


def test_parent_matches_any_of_several_and_flags_multiple_as_info():
    ecarts = diagnose(_wd(parent_names=["Felis", "Panthera"]), _src())
    assert _types(ecarts) == ["parents_multiples"]
    assert ecarts[0].severite == "info"


def test_parent_mismatch_is_error():
    (e,) = diagnose(_wd(parent_names=["Felis"]), _src())
    assert (e.type, e.severite) == ("parent_different", "erreur")


def test_synonyms_both_directions_ignoring_case():
    wd = _wd(synonyms=["Felis leo", "Leo leo"])
    src = _src(synonyms=["felis leo", "Panthera leo leo"])
    ecarts = diagnose(wd, src)
    assert _types(ecarts) == ["synonyme_absent_source", "synonyme_absent_wikidata"]
    by_type = {e.type: e for e in ecarts}
    assert by_type["synonyme_absent_wikidata"].valeur_source == "Panthera leo leo"
    assert by_type["synonyme_absent_source"].valeur_wikidata == "Leo leo"
    assert by_type["synonyme_absent_wikidata"].severite == "info"  # cible non résolue
    assert by_type["synonyme_absent_source"].severite == "info"


def test_id_equal_or_one_of_several_is_not_a_gap():
    wd = _wd(external_ids={"gbif": ["111", "222"], "itis": ["5"]})
    src = _src(external_ids={"gbif": "222", "itis": "5"})
    assert diagnose(wd, src) == []


def test_id_different_is_warning():
    (e,) = diagnose(_wd(external_ids={"itis": ["5"]}), _src(external_ids={"itis": "6"}))
    assert (e.type, e.severite, e.propriete) == ("identifiant_different", "avertissement", "itis")
    assert (e.valeur_wikidata, e.valeur_source) == ("5", "6")


def test_id_absent_on_wikidata_and_absent_in_source_is_silent():
    wd = _wd(external_ids={"eol": ["9"]})
    src = _src(external_ids={"itis": "6"})
    (e,) = diagnose(wd, src)
    assert (e.type, e.propriete, e.valeur_source) == ("identifiant_absent_wikidata", "itis", "6")


def test_int_source_ids_are_compared_as_strings():
    assert diagnose(_wd(external_ids={"inpn": ["644245"]}), _src(external_ids={"inpn": 644245})) == []


def test_missing_reference_not_confirmed_by_source_is_info_without_proposal():
    stmt = StatementSansReference(
        propriete="P225", valeur="Felis leo", type="chaine", nom="Felis leo"
    )
    wd = _wd(names=["Panthera leo", "Felis leo"], unreferenced=[stmt])
    (e,) = diagnose(wd, _src(), _ctx())
    assert (e.type, e.severite, e.proposition) == ("reference_manquante", "info", None)


# --- propositions ---------------------------------------------------------------------------


def test_missing_id_with_known_property_is_a_suggestion_with_referenced_proposal():
    (e,) = diagnose(_wd(), _src(external_ids={"itis": "6"}), _ctx())
    assert (e.type, e.severite, e.propriete) == (
        "identifiant_absent_wikidata",
        "suggestion",
        "itis",
    )
    p = e.proposition
    assert (p.module, p.propriete, p.valeur, p.type) == ("itis", "P815", "6", "chaine")
    assert (p.reference.stated_in, p.reference.retrieved) == ("Q82575", date(2026, 9, 24))
    assert p.verifiee and p.coche_par_defaut


def test_id_proposal_applies_the_property_prefix():
    ctx = _ctx(database_items={"powo": "Q47542613"})
    (e,) = diagnose(_wd(), _src(external_ids={"powo": "304293-2"}), ctx)
    assert e.proposition.valeur == "urn:lsid:ipni.org:names:304293-2"


def test_unverified_property_is_unchecked_by_default():
    ctx = _ctx(proprietes_a_verifier=frozenset({"P815"}))
    (e,) = diagnose(_wd(), _src(external_ids={"itis": "6"}), ctx)
    assert (e.proposition.verifiee, e.proposition.coche_par_defaut) == (False, False)


def test_id_without_property_mapping_or_database_item_gets_no_proposal():
    (e,) = diagnose(_wd(), _src(external_ids={"wrms": "6"}), _ctx())
    assert (e.severite, e.proposition) == ("info", None)
    (e,) = diagnose(_wd(), _src(external_ids={"itis": "6"}), _ctx(database_items={}))
    assert (e.severite, e.proposition) == ("info", None)


def test_missing_rank_is_a_suggestion_with_the_rank_item():
    (e,) = diagnose(_wd(rank=None), _src(), _ctx())
    assert (e.type, e.severite) == ("rang_absent_wikidata", "suggestion")
    p = e.proposition
    assert (p.module, p.propriete, p.valeur, p.type) == ("col", "P105", "Q7432", "item")
    assert p.reference.stated_in == "Q38840"


def test_missing_rank_without_rank_item_gets_no_proposal():
    (e,) = diagnose(_wd(rank=None), _src(), _ctx(rank_qid=None))
    assert (e.severite, e.proposition) == ("info", None)


def test_missing_parent_needs_a_resolved_unambiguous_target():
    (e,) = diagnose(_wd(parent_names=[]), _src(), _ctx(resolved_items={"Panthera": "Q127960"}))
    assert e.severite == "suggestion"
    p = e.proposition
    assert (p.propriete, p.valeur, p.type) == ("P171", "Q127960", "item")
    for resolved in ({"Panthera": None}, {}):
        (e,) = diagnose(_wd(parent_names=[]), _src(), _ctx(resolved_items=resolved))
        assert (e.severite, e.proposition) == ("info", None)
        assert "à créer" in e.message


def test_synonym_absent_from_wikidata_is_a_suggestion_when_target_resolved():
    src = _src(synonyms=["Felis leo"])
    (e,) = diagnose(_wd(), src, _ctx(resolved_items={"Felis leo": "Q900"}))
    assert (e.type, e.severite) == ("synonyme_absent_wikidata", "suggestion")
    assert (e.proposition.propriete, e.proposition.valeur) == ("P1420", "Q900")


def test_synonym_absent_from_source_is_info_and_never_proposed():
    (e,) = diagnose(_wd(synonyms=["Leo leo"]), _src(), _ctx())
    assert (e.type, e.severite, e.proposition) == ("synonyme_absent_source", "info", None)


def test_missing_reference_confirmed_by_source_is_a_suggestion():
    stmt = StatementSansReference(
        propriete="P225", valeur="Panthera leo", type="chaine", nom="Panthera leo"
    )
    (e,) = diagnose(_wd(unreferenced=[stmt]), _src(), _ctx())
    assert (e.type, e.severite, e.propriete) == ("reference_manquante", "suggestion", "P225")
    assert (e.proposition.valeur, e.proposition.reference.stated_in) == ("Panthera leo", "Q38840")


def test_missing_reference_on_parent_statement_uses_its_qid():
    stmt = StatementSansReference(
        propriete="P171", valeur="Q127960", type="item", nom="Panthera"
    )
    (e,) = diagnose(_wd(unreferenced=[stmt]), _src(), _ctx())
    p = e.proposition
    assert (e.severite, p.valeur, p.type) == ("suggestion", "Q127960", "item")


def test_proposal_id_is_deterministic_and_distinguishes_values():
    def prop(qid="Q140", value="6"):
        (e,) = diagnose(_wd(qid=qid), _src(external_ids={"itis": value}), _ctx())
        return e.proposition.id

    assert prop() == prop()
    assert len({prop(), prop(value="7"), prop(qid="Q1")}) == 3


def test_errors_never_carry_a_proposal():
    ecarts = diagnose(_wd(rank="genre", parent_names=["Felis"]), _src(), _ctx())
    assert {e.severite for e in ecarts} == {"erreur"}
    assert {e.proposition for e in ecarts} == {None}
