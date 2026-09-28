"""/generate et /generate/stream partagent un même calcul mis en cache (voir
organon.api.generation_cache) ; un échec n'est jamais conservé."""

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
def calls(monkeypatch):
    monkeypatch.setenv("ORGANON_DEV", "1")
    limiter.reset()
    generate._generation_cache.clear()
    seen: list[tuple[str, str, str]] = []

    async def fake_attempt(module_id, module, req, options):
        seen.append((module_id, req.taxon, req.domain))
        struct = Struct(
            taxon=TaxonInfo(name=req.taxon, rank="espèce"),
            classification=req.classification,
            domain=req.domain,
            kingdom="animal",
        )
        return module_id, struct, None

    monkeypatch.setattr(generate, "_attempt_classification", fake_attempt)

    async def no_enrichment(self):
        return
        yield  # pragma: no cover — fait de `run` un générateur asynchrone

    monkeypatch.setattr(generate.EnrichmentRunner, "run", no_enrichment)
    yield seen
    generate._generation_cache.clear()


@pytest.fixture
def client():
    return TestClient(app_module.create_app())


def _events(response):
    return [
        json.loads(line[len("data: "):])
        for line in response.text.split("\n\n")
        if line.startswith("data: ")
    ]


def test_two_identical_generations_compute_only_once(client, calls):
    first = client.post(GENERATE, json={"taxon": "Panthera leo"})
    n = len(calls)
    assert first.status_code == 200 and n > 0
    second = client.post(GENERATE, json={"taxon": "Panthera leo"})
    assert second.json() == first.json()
    assert len(calls) == n


def test_stream_reuses_the_generate_computation(client, calls):
    client.post(GENERATE, json={"taxon": "Panthera leo"})
    n = len(calls)
    events = _events(client.post(STREAM, json={"taxon": "Panthera leo"}))
    assert len(calls) == n
    assert events[-1]["type"] == "result"
    assert any(e["type"] == "plan" for e in events)


def test_generate_reuses_the_stream_computation(client, calls):
    events = _events(client.post(STREAM, json={"taxon": "Panthera leo"}))
    n = len(calls)
    resp = client.post(GENERATE, json={"taxon": "Panthera leo"})
    assert len(calls) == n
    assert resp.json() == events[-1]["data"]


def test_different_requests_computed_separately(client, calls):
    client.post(GENERATE, json={"taxon": "Panthera leo"})
    n = len(calls)
    client.post(GENERATE, json={"taxon": "Panthera leo", "domain": "animal"})
    assert len(calls) > n


def test_taxon_not_found_is_not_cached(client, monkeypatch, calls):
    async def not_found(module_id, module, req, options):
        calls.append((module_id, req.taxon, req.domain))
        return module_id, None, None

    monkeypatch.setattr(generate, "_attempt_classification", not_found)
    assert client.post(GENERATE, json={"taxon": "Xus yus"}).status_code == 404
    n = len(calls)
    assert client.post(GENERATE, json={"taxon": "Xus yus"}).status_code == 404
    assert len(calls) == 2 * n


def test_stream_reports_a_taxon_not_found(client, monkeypatch, calls):
    async def not_found(module_id, module, req, options):
        return module_id, None, None

    monkeypatch.setattr(generate, "_attempt_classification", not_found)
    events = _events(client.post(STREAM, json={"taxon": "Xus yus"}))
    assert events[-1]["type"] == "fatal_error"
    assert events[-1]["status_code"] == 404


def test_unknown_module_remains_an_http_error(client, calls):
    r = client.post(GENERATE, json={"taxon": "Panthera leo", "classification": "inconnu"})
    assert r.status_code == 400
    r = client.post(STREAM, json={"taxon": "Panthera leo", "classification": "inconnu"})
    assert r.status_code == 400
