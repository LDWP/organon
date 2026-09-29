"""Tests du module Wikidata : extraction de claims par WikidataEntityAdapter
(fonctions pures sur un entity JSON déjà récupéré)."""

from __future__ import annotations

import httpx
import respx

from organon.modules.wikidata.adapter import WikidataEntityAdapter

APIS_MELLIFERA_ENTITY = {
    "claims": {
        "P225": [{"mainsnak": {"datavalue": {"value": "Apis mellifera"}}}],
        "P846": [{"mainsnak": {"datavalue": {"value": "1341976"}}}],
        "P815": [{"mainsnak": {"datavalue": {"value": "154395"}}}],
        "P405": [{"mainsnak": {"datavalue": {"value": {"id": "Q1035"}}}}],
        "P574": [{"mainsnak": {"datavalue": {"value": {"time": "+1758-01-01T00:00:00Z"}}}}],
    },
    "labels": {"fr": {"value": "Abeille domestique"}},
}


def test_taxon_name():
    adapter = WikidataEntityAdapter()
    assert adapter.taxon_name(APIS_MELLIFERA_ENTITY) == "Apis mellifera"


def test_taxon_name_absent():
    adapter = WikidataEntityAdapter()
    assert adapter.taxon_name({"claims": {}}) is None


def test_external_ids_keeps_new_gbif_schema_over_legacy():
    entity = {
        "claims": {
            "P846": [{"mainsnak": {"datavalue": {"value": "old-legacy-id"}}}],
            "P14607": [{"mainsnak": {"datavalue": {"value": "new-id"}}}],
        }
    }
    adapter = WikidataEntityAdapter()
    assert adapter.external_ids(entity)["gbif"] == "new-id"


def test_external_ids_from_full_entity():
    adapter = WikidataEntityAdapter()
    assert adapter.external_ids(APIS_MELLIFERA_ENTITY) == {
        "gbif": "1341976",
        "itis": "154395",
    }


def test_external_ids_covers_inpn_iucn_vascan():
    # Valeurs réelles : Panthera leo (Q140 : P3186, P627) et Quercus robur (Q165145 : P1745),
    # identiques aux `id` produits par les modules inpn/iucn/vascan sur ces taxons.
    entity = {
        "claims": {
            "P3186": [{"mainsnak": {"datavalue": {"value": "644245"}}}],
            "P627": [{"mainsnak": {"datavalue": {"value": "15951"}}}],
            "P1745": [{"mainsnak": {"datavalue": {"value": "5969"}}}],
        }
    }
    assert WikidataEntityAdapter().external_ids(entity) == {
        "inpn": "644245",
        "iucn": "15951",
        "vascan": "5969",
    }


def test_rank_qids_map_to_known_organon_ranks():
    from importlib.resources import files

    import yaml

    from organon.modules.wikidata.adapter import RANK_QIDS

    known = yaml.safe_load(
        files("organon.core.data").joinpath("ranks.yaml").read_text(encoding="utf-8")
    )["ranks"]
    assert set(RANK_QIDS.values()) <= set(known)
    # Q7432 = species, Q34740 = genus, Q713623 = clade (vérifiés en direct sur wikidata.org)
    assert RANK_QIDS["Q7432"] == "espèce"
    assert RANK_QIDS["Q34740"] == "genre"
    assert RANK_QIDS["Q713623"] == "clade"


def test_rank_of_reads_p105_qid():
    entity = {"claims": {"P105": [{"mainsnak": {"datavalue": {"value": {"id": "Q7432"}}}}]}}
    assert WikidataEntityAdapter().rank(entity) == "espèce"
    assert WikidataEntityAdapter().rank({"claims": {}}) is None


def _snak(value, rank="normal", qualifiers=None, references=None):
    statement = {"mainsnak": {"datavalue": {"value": value}}, "rank": rank}
    if qualifiers:
        statement["qualifiers"] = qualifiers
    if references:
        statement["references"] = references
    return statement


def test_statements_ignores_deprecated_and_keeps_rank_qualifiers_references():
    entity = {
        "claims": {
            "P171": [
                _snak({"id": "Q1"}, rank="preferred"),
                _snak({"id": "Q2"}),
                _snak({"id": "Q3"}, rank="deprecated"),
            ],
            "P225": [
                _snak(
                    "Panthera leo",
                    qualifiers={"P405": [{"datavalue": {"value": {"id": "Q1043"}}}]},
                    references=[{"snaks": {"P248": [{"datavalue": {"value": {"id": "Q13"}}}]}}],
                )
            ],
        }
    }
    adapter = WikidataEntityAdapter()

    parents = adapter.statements(entity, "P171")
    assert [(s.value["id"], s.rank) for s in parents] == [("Q1", "preferred"), ("Q2", "normal")]

    (name,) = adapter.statements(entity, "P225")
    assert name.qualifiers == {"P405": [{"id": "Q1043"}]}
    assert name.references == [{"P248": [{"id": "Q13"}]}]


def test_statements_skips_novalue_and_missing_property():
    entity = {"claims": {"P105": [{"mainsnak": {"snaktype": "novalue"}, "rank": "normal"}]}}
    adapter = WikidataEntityAdapter()
    assert adapter.statements(entity, "P105") == []
    assert adapter.statements(entity, "P999") == []


def test_external_id_values_keeps_all_values_even_beyond_first_statement():
    entity = {
        "claims": {
            "P846": [_snak("111"), _snak("222")],
            "P14607": [_snak("new")],
            "P815": [_snak("999", rank="deprecated")],
        }
    }
    assert WikidataEntityAdapter().external_id_values(entity) == {"gbif": ["111", "222", "new"]}


@respx.mock
async def test_get_entities_batches_ids_by_50():
    ids = [f"Q{n}" for n in range(1, 121)]
    def respond(request: httpx.Request) -> httpx.Response:
        entities = {
            q: ({"id": q, "missing": ""} if q == "Q2" else {"id": q})
            for q in request.url.params["ids"].split("|")
        }
        return httpx.Response(200, json={"entities": entities})

    route = respx.get("https://www.wikidata.org/w/api.php").mock(side_effect=respond)
    adapter = WikidataEntityAdapter()
    try:
        result = await adapter.get_entities(ids)
    finally:
        await adapter.aclose()

    assert route.call_count == 3
    assert len(result) == 119
    assert "Q2" not in result
    assert result["Q120"] == {"id": "Q120"}
