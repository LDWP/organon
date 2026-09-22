from __future__ import annotations

from datetime import date

from organon.core.update_diagnosis import (
    ContextePropositions,
    IdentifiantWikidata,
    SourceView,
    build_creation,
)


def _src(**kw) -> SourceView:
    base = dict(
        source="col",
        name="Panthera leo",
        rank="espèce",
        parent_name="Panthera",
        synonyms=[],
        external_ids={"itis": "183803", "gbif": "5219404"},
        redirected_from=None,
    )
    return SourceView(**{**base, **kw})


def _ctx(**kw) -> ContextePropositions:
    base = dict(
        retrieved=date(2026, 10, 3),
        database_items={"col": "Q38840", "itis": "Q82575"},
        rank_qid="Q7432",
        resolved_items={"Panthera": "Q127960"},
        id_properties={
            "itis": IdentifiantWikidata(propriete="P815"),
            "gbif": IdentifiantWikidata(propriete="P846"),
        },
    )
    return ContextePropositions(**{**base, **kw})


def _lignes(creation):
    return [(ligne.propriete, ligne.valeur, ligne.type) for ligne in creation.lignes]


def test_creation_complete_avec_references():
    creation = build_creation(_src(), _ctx())
    assert creation.label == "Panthera leo"
    assert _lignes(creation) == [
        ("P31", "Q16521", "item"),
        ("P225", "Panthera leo", "chaine"),
        ("P105", "Q7432", "item"),
        ("P171", "Q127960", "item"),
        ("P815", "183803", "chaine"),
    ]
    by_prop = {ligne.propriete: ligne.reference for ligne in creation.lignes}
    assert by_prop["P31"] is None
    assert by_prop["P225"].stated_in == "Q38840"
    assert by_prop["P815"].stated_in == "Q82575"
    assert by_prop["P815"].retrieved == date(2026, 10, 3)


def test_ligne_sans_item_de_base_ou_sans_propriete_est_omise():
    # gbif : propriété connue mais pas d'item « stated in » dans database_items
    assert "P846" not in [ligne.propriete for ligne in build_creation(_src(), _ctx()).lignes]


def test_parent_non_resolu_ou_rang_inconnu_omis_sans_choix_arbitraire():
    creation = build_creation(_src(), _ctx(resolved_items={"Panthera": None}, rank_qid=None))
    assert [ligne.propriete for ligne in creation.lignes] == ["P31", "P225", "P815"]


def test_synonyme_suivi_par_la_source_pas_de_creation():
    # La source décrit le taxon accepté : ses rang/parent/ids ne sont pas ceux du nom demandé.
    assert build_creation(_src(redirected_from="Felis leo"), _ctx()) is None


def test_id_stable_et_dependant_du_contenu():
    assert build_creation(_src(), _ctx()).id == build_creation(_src(), _ctx()).id
    assert build_creation(_src(), _ctx()).id != build_creation(
        _src(external_ids={"itis": "1"}), _ctx()
    ).id


def test_prefixe_de_l_identifiant_applique():
    ctx = _ctx(
        database_items={"col": "Q38840", "powo": "Q47542613"},
        id_properties={"powo": IdentifiantWikidata(propriete="P5037", prefixe="urn:lsid:x:")},
    )
    creation = build_creation(_src(external_ids={"powo": "77"}), ctx)
    assert ("P5037", "urn:lsid:x:77", "chaine") in _lignes(creation)


# --- lot 2b : statut UICN et synonymes -----------------------------------------------------------

from organon.core.update_diagnosis import (  # noqa: E402
    WikidataView,
    build_synonym_creation,
    diagnose,
)


def _ctx_uicn(**kw):
    return _ctx(
        database_items={"col": "Q38840", "itis": "Q82575", "iucn": "Q32059"},
        statut_qids={"VU": "Q278113", "EN": "Q96377276"},
        **kw,
    )


def test_creation_porte_le_statut_uicn_reference_iucn():
    creation = build_creation(_src(uicn="VU"), _ctx_uicn())
    ligne = next(li for li in creation.lignes if li.propriete == "P141")
    assert (ligne.valeur, ligne.type, ligne.reference.stated_in) == ("Q278113", "item", "Q32059")


def test_statut_uicn_inconnu_omis():
    creation = build_creation(_src(uicn="NE"), _ctx_uicn())
    assert "P141" not in [li.propriete for li in creation.lignes]


def _wd(**kw) -> WikidataView:
    base = dict(
        qid="Q140", is_taxon=True, names=["Panthera leo"], rank="espèce",
        parent_names=["Panthera"], synonyms=[], external_ids={}, unreferenced=[],
    )
    return WikidataView(**{**base, **kw})


def _types(ecarts):
    return {e.type: e for e in ecarts}


def test_uicn_absent_de_wikidata_est_une_suggestion_referencee():
    ecart = _types(diagnose(_wd(), _src(uicn="VU", external_ids={}), _ctx_uicn()))[
        "uicn_absent_wikidata"
    ]
    assert ecart.severite == "suggestion"
    assert (ecart.proposition.propriete, ecart.proposition.valeur) == ("P141", "Q278113")
    assert ecart.proposition.reference.stated_in == "Q32059"


def test_uicn_different_est_un_avertissement_sans_proposition():
    ecart = _types(diagnose(_wd(uicn=["Q96377276"]), _src(uicn="VU", external_ids={}), _ctx_uicn()))[
        "uicn_different"
    ]
    assert (ecart.severite, ecart.valeur_wikidata, ecart.valeur_source) == (
        "avertissement", "EN", "VU"
    )
    assert ecart.proposition is None


def test_uicn_identique_ou_source_muette_aucun_ecart():
    assert "uicn_different" not in _types(
        diagnose(_wd(uicn=["Q278113"]), _src(uicn="VU", external_ids={}), _ctx_uicn())
    )
    assert not any(
        t.startswith("uicn") for t in _types(diagnose(_wd(), _src(external_ids={}), _ctx_uicn()))
    )


def test_synonyme_cree_lie_a_l_item_accepte_dans_les_deux_sens():
    creation = build_synonym_creation("Felis leo", "Q140", _src(), _ctx())
    assert creation.label == "Felis leo"
    assert _lignes(creation) == [
        ("P31", "Q16521", "item"),
        ("P225", "Felis leo", "chaine"),
        ("P1420", "Q140", "item"),
    ]
    assert creation.lignes[1].reference.stated_in == "Q38840"
    [retour] = creation.rattachements
    assert (retour.qid, retour.propriete, retour.reference.stated_in) == ("Q140", "P1420", "Q38840")
    assert creation.coche_par_defaut is False


def test_synonyme_absent_avec_item_a_creer_porte_une_creation_decochee():
    ctx = _ctx(noms_absents=frozenset({"Felis leo"}))
    ecart = _types(diagnose(_wd(), _src(synonyms=["Felis leo"], external_ids={}), ctx))[
        "synonyme_absent_wikidata"
    ]
    assert ecart.severite == "suggestion" and ecart.proposition is None
    assert ecart.creation.label == "Felis leo"
    assert ecart.creation.rattachements[0].qid == "Q140"


def test_synonyme_ambigu_ou_inconnu_reste_une_info():
    ecart = _types(diagnose(_wd(), _src(synonyms=["Felis leo"], external_ids={}), _ctx()))[
        "synonyme_absent_wikidata"
    ]
    assert ecart.severite == "info" and ecart.creation is None
