"""Contrat de noms de champs de l'API de génération : requête, réponse et inventaire des sources.

Les clés sont en anglais ; seules les valeurs (rangs, règnes, libellés) restent en français.
"""

from __future__ import annotations

from organon.api.routes.generate import _assemble_response, _select_main_author
from organon.api.schemas import GenerateRequest
from organon.core.db_inventory import load_db_inventory
from organon.core.models import (
    Basionym,
    KingdomInconsistency,
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
    TaxonInfo,
)

REQUEST_FIELDS = {
    "taxon",
    "classification",
    "domain",
    "gbif_key",
    "author_source",
    "synonym_links",
    "infraspecific_links",
    "follow_synonyms",
    "sort_synonyms",
    "external_only",
    "selectors",
    "plan",
    "column_threshold",
    "list_limit",
    "timeout",
    "off",
    "marine_only",
    "homonym_category_key",
}

RESPONSE_FIELDS = {
    "requested_taxon",
    "resolved_taxon",
    "taxon_rank",
    "used_classification",
    "used_domain",
    "kingdom",
    "extinct",
    "iucn_status",
    "iucn_criterion",
    "vernacular_names",
    "vernacular_names_without_language",
    "other_names",
    "wikitext",
    "taxobox_wikitext",
    "subtaxa_wikitext",
    "subtaxa",
    "subtaxa_source",
    "classification_taxobox",
    "see_also_wikitext",
    "references_wikitext",
    "reference_items",
    "taxobox_completeness_score",
    "subtaxa_completeness_score",
    "rank_lines",
    "external_links",
    "data_found",
    "author_candidates",
    "consolidated_author",
    "resolved_author",
    "synonyms",
    "synonyms_source",
    "basionym",
    "logs",
    "warnings",
    "elapsed_seconds",
    "truncated",
    "kingdom_inconsistencies",
    "rank_inconsistencies",
    "habitat",
    "distribution",
    "distribution_entries",
    "external_ids",
}


def _assemble(struct):
    req = GenerateRequest(taxon="Panthera leo")
    candidates = _select_main_author(struct, req, "col")
    return _assemble_response(req, req, "col", struct, [], [], [], 0.0, candidates)


def test_request_field_names():
    assert set(GenerateRequest.model_fields) == REQUEST_FIELDS


def test_response_field_names():
    resp = _assemble(Struct(taxon=TaxonInfo(name="Panthera leo", rank="espèce")))
    assert set(resp.model_dump()) == RESPONSE_FIELDS


def test_nested_field_names_in_response():
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo", rank="espèce"),
        subtaxa=SubTaxonList(items=[RankName(name="Panthera leo leo", rank="sous-espèce")]),
        synonyms=SynonymList(items=[RankName(name="Felis leo", author="L.", extinct=False)]),
        basionym=Basionym(name="Felis leo", author="L.", source="col"),
    )
    resp = _assemble(struct).model_dump()
    assert set(resp["subtaxa"][0]) == {"name", "rank", "author", "extinct"}
    assert set(resp["synonyms"][0]) == {"name", "rank", "author", "extinct"}
    assert set(resp["basionym"]) == {"name", "author", "source"}


def test_values_stay_in_french():
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo", rank="espèce"),
        kingdom="animal",
        subtaxa=SubTaxonList(items=[RankName(name="Panthera leo leo", rank="sous-espèce")]),
    )
    resp = _assemble(struct)
    assert (resp.taxon_rank, resp.kingdom) == ("espèce", "animal")
    assert resp.subtaxa[0].rank == "sous-espèce"


def test_inconsistency_field_names():
    inconsistency = KingdomInconsistency(
        module="itis", suggested_kingdom="végétal", retained_kingdom="animal"
    )
    assert set(inconsistency.model_dump()) == {"module", "suggested_kingdom", "retained_kingdom"}


def test_inventory_field_names():
    inventory = load_db_inventory().model_dump()
    assert set(inventory) == {"last_updated", "categories"}
    category = inventory["categories"][0]
    assert set(category) == {"id", "name", "sources"}
    assert set(category["sources"][0]) == {
        "id",
        "name",
        "url",
        "status",
        "classification",
        "harvested_items",
        "facets",
        "access",
        "last_updated",
        "notes",
        "is_default",
    }
    assert set(category["sources"][0]["classification"]) == {
        "can_classify",
        "estimated",
        "detail",
    }
