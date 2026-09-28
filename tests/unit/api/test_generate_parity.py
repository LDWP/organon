"""/generate and /generate/stream must return the same result for the same taxon, and the
author vote / enrichment plan helpers must agree with each other."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from organon.api import app as app_module
from organon.api.rate_limit import limiter
from organon.api.routes import generate
from organon.core.models import Struct, TaxonInfo

GENERATE = "/api/v1/generate"
STREAM = "/api/v1/generate/stream"


@pytest.fixture
def mocked_taxon(monkeypatch):
    monkeypatch.setenv("ORGANON_DEV", "1")
    limiter.reset()
    generate._generation_cache.clear()

    async def fake_attempt(module_id, module, req, options):
        struct = Struct(
            taxon=TaxonInfo(name=req.taxon, rank="espèce", author="Linnaeus, 1758"),
            classification=req.classification,
            domain=req.domain,
            kingdom="animal",
        )
        return module_id, struct, None

    async def fake_collect(self, module_id):
        struct = self.struct.model_copy(deep=True)
        struct.habitat = "marin"
        return module_id, struct, None

    monkeypatch.setattr(generate, "_attempt_classification", fake_attempt)
    monkeypatch.setattr(generate.EnrichmentRunner, "collect_one_module", fake_collect)
    yield
    generate._generation_cache.clear()


@pytest.fixture
def client():
    return TestClient(app_module.create_app())


def _stream_result(response):
    events = [
        json.loads(line[len("data: "):])
        for line in response.text.split("\n\n")
        if line.startswith("data: ")
    ]
    return events[-1]["data"]


def test_generate_and_stream_return_the_same_result(client, mocked_taxon):
    body = {"taxon": "Panthera leo"}
    plain = client.post(GENERATE, json=body).json()
    generate._generation_cache.clear()  # no shared cache: compare two independent computations
    streamed = _stream_result(client.post(STREAM, json=body))
    plain.pop("elapsed_seconds")
    streamed.pop("elapsed_seconds")
    assert plain == streamed
    assert plain["habitat"] == "marin"  # enrichment really ran


def _struct(**link_authors):
    return Struct(
        taxon=TaxonInfo(name="x", author="A"),
        links={m: {"author": a} for m, a in link_authors.items()},
    )


def test_author_candidates_link_entry_overrides_classification_author():
    struct = _struct(col="B", gbif="C")
    assert generate._author_candidates(struct, "col") == {"col": "B", "gbif": "C"}


def _vote(struct, classification_id="col"):
    candidates = generate._author_candidates(struct, classification_id)
    return generate._majority_author(candidates, struct, classification_id)


def test_classification_link_author_is_exposed_but_does_not_vote():
    struct = Struct(taxon=TaxonInfo(name="x"), links={"col": {"author": " B "}})
    assert generate._author_candidates(struct, "col") == {"col": "B"}
    assert _vote(struct) == ""


def test_classification_link_does_not_get_a_second_voice():
    assert _vote(_struct(col="B", gbif="C", itis="C")) == "C"
    assert _vote(_struct(col="B", gbif="C")) == "A"


def test_majority_vote_beats_classification_author():
    assert _vote(_struct(gbif="B", itis="B")) == "B"


def test_majority_vote_tie_goes_to_classification_author():
    assert _vote(_struct(gbif="B")) == "A"


def test_majority_vote_tie_without_classification_author_takes_first():
    struct = Struct(
        taxon=TaxonInfo(name="x"), links={"gbif": {"author": "B"}, "itis": {"author": "C"}}
    )
    assert _vote(struct) == "B"


def test_majority_vote_empty():
    assert _vote(Struct(taxon=TaxonInfo(name="x"))) == ""

def test_monovalue_fields_follow_struct():
    namespaced = {"links", "vernacular", "other_names", "description", "distribution", "domain"}
    assert set(generate._MONOVALUE_FIELDS) == set(Struct.model_fields) - namespaced


def test_runner_exposes_enrichment_ids_sorted_by_priority(monkeypatch):
    monkeypatch.setattr(generate, "get_module", lambda m: object())
    runner = generate.EnrichmentRunner(
        Struct(taxon=TaxonInfo(name="x")),
        "col",
        ["col", "b", "a", "off"],
        {"off"},
        generate.GenerateOptions(),
        {"a": 1, "b": 5},
    )
    assert runner.enrichment_ids == ["a", "b"]
