"""Champs de GenerateResponse dont le diagnostic frwiki a besoin (UICN, sous-taxons,
répartition, bloc « voir aussi », code Taxobox)."""

from __future__ import annotations

from organon.api.routes.generate import _assemble_response, _select_main_author
from organon.api.schemas import GenerateRequest
from organon.core.models import DistributionEntry, RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.rendering.engine import sections


def _assemble(struct):
    req = GenerateRequest(taxon="Panthera leo")
    candidates = _select_main_author(struct, req, "col")
    return _assemble_response(req, req, "col", struct, [], [], [], 0.0, candidates)


def _struct(**kw):
    return Struct(taxon=TaxonInfo(name="Panthera leo", rank="espèce"), **kw)


def test_iucn_criterion_exposed():
    resp = _assemble(_struct(links={"iucn": {"risk": "VU", "criterion": "C1"}}))
    assert (resp.iucn_status, resp.iucn_criterion) == ("VU", "C1")


def test_iucn_criterion_empty_without_assessment():
    assert _assemble(_struct()).iucn_criterion == ""


def test_subtaxa_source_and_taxobox_code_exposed():
    struct = _struct(
        classification_taxobox="COL",
        subtaxa=SubTaxonList(items=[RankName(name="Panthera leo leo")], source="col"),
    )
    resp = _assemble(struct)
    assert resp.subtaxa_source == "col"
    assert resp.classification_taxobox == "COL"


def test_detailed_breakdown_exposed_per_module():
    entry = DistributionEntry(certain={"MG": "MG"}, extinct={"MG": "MG"})
    resp = _assemble(_struct(distribution={"powo": entry}))
    assert resp.distribution_entries == {"powo": entry}


def test_see_also_block_exposed_as_rendered():
    struct = _struct()
    req = GenerateRequest(taxon="Panthera leo")
    resp = _assemble(struct)
    assert resp.see_also_wikitext == sections.render_see_also(struct, req)


def test_names_without_language_code_exposed_per_module_and_outside_french_summary():
    resp = _assemble(
        _struct(
            vernacular={
                "GBIF": {"fr": ["Loup gris"], "und": ["Canis"]},
                "ITIS": {"en": ["Gray wolf"]},
            }
        )
    )
    assert resp.vernacular_names_without_language == {"GBIF": ["Canis"]}
    assert resp.vernacular_names == ["Loup gris"]
