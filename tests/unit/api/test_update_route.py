import httpx
import pytest
import respx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from organon.api import app as app_module
from organon.api.rate_limit import limiter
from organon.core.update_diagnosis import DiagnosticResponse
from organon.modules.wikidata import diagnosis
from organon.modules.wikidata.diagnosis import AmbiguousTaxonError, TaxonNotFoundError

URL = "/api/v1/update/diagnose"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORGANON_DEV", "1")
    limiter.reset()
    return TestClient(app_module.create_app())


def _patch(monkeypatch, result=None, exc=None):
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        if exc:
            raise exc
        return result

    monkeypatch.setattr("organon.api.routes.update.diagnose_taxon", fake)
    return calls


def test_auth_required(client, monkeypatch):
    monkeypatch.delenv("ORGANON_DEV")
    assert client.post(URL, json={"taxon": "Panthera leo"}).status_code == 401


def test_nominal(client, monkeypatch):
    calls = _patch(monkeypatch, DiagnosticResponse(qid="Q140", taxon="Panthera leo"))
    r = client.post(URL, json={"taxon": "Panthera leo", "classification": "gbif"})
    assert r.status_code == 200
    assert r.json()["qid"] == "Q140"
    assert calls[0]["taxon"] == "Panthera leo"
    assert calls[0]["classification"] == "gbif"
    assert calls[0]["generate"] is not None


def test_taxon_or_qid_required(client):
    assert client.post(URL, json={}).status_code == 422


def test_taxon_not_found_404(client, monkeypatch):
    _patch(monkeypatch, exc=TaxonNotFoundError("Q0"))
    assert client.post(URL, json={"qid": "Q0"}).status_code == 404


def test_generate_404(client, monkeypatch):
    _patch(monkeypatch, exc=HTTPException(404, detail="inconnu"))
    assert client.post(URL, json={"taxon": "Xx"}).status_code == 404


def test_ambiguous_409_lists_candidates(client, monkeypatch):
    _patch(monkeypatch, exc=AmbiguousTaxonError(["Q1", "Q2"]))
    r = client.post(URL, json={"taxon": "Morus"})
    assert r.status_code == 409
    assert r.json()["detail"]["candidates"] == ["Q1", "Q2"]


def test_httpx_502(client, monkeypatch):
    _patch(monkeypatch, exc=httpx.ConnectError("boom"))
    assert client.post(URL, json={"taxon": "Xx"}).status_code == 502


def test_httpx_502_message_names_exception_and_host(client, monkeypatch):
    request = httpx.Request("GET", "https://query.wikidata.org/sparql")
    _patch(monkeypatch, exc=httpx.ReadTimeout("", request=request))
    r = client.post(URL, json={"taxon": "Xx"})
    assert r.status_code == 502
    assert r.json()["detail"] == "Requête réseau échouée : ReadTimeout (query.wikidata.org)"


def test_httpx_502_message_without_request(client, monkeypatch):
    _patch(monkeypatch, exc=httpx.ConnectError("boom"))
    r = client.post(URL, json={"taxon": "Xx"})
    assert r.json()["detail"] == "Requête réseau échouée : ConnectError (boom)"


def test_rate_limit(client, monkeypatch):
    _patch(monkeypatch, DiagnosticResponse(qid=None, taxon="x"))
    codes = [client.post(URL, json={"taxon": "x"}).status_code for _ in range(41)]
    assert codes[:40] == [200] * 40
    assert codes[40] == 429


def test_module_imported():
    assert diagnosis.diagnose_taxon


EXPORT_URL = "/api/v1/update/export"


def _diag_with_props():
    from datetime import date

    from organon.core.update_diagnosis import Ecart, Proposition, Reference

    def prop(pid, valeur):
        return Proposition(
            id=pid,
            module="gbif",
            propriete="P846",
            valeur=valeur,
            type="chaine",
            reference=Reference(stated_in="Q1531570", retrieved=date(2026, 9, 24)),
        )

    def gap(p):
        return Ecart(
            type="identifiant_absent_wikidata",
            severite="suggestion",
            propriete="P846",
            source="gbif",
            message="m",
            proposition=p,
        )

    return DiagnosticResponse(qid="Q140", taxon="Panthera leo", ecarts=[
        gap(prop("aaa", "111")),
        gap(prop("bbb", "222")),
        Ecart(type="info", severite="info", propriete="P225", source="gbif", message="m"),
    ])


def test_export_auth_required(client, monkeypatch):
    monkeypatch.delenv("ORGANON_DEV")
    r = client.post(EXPORT_URL, json={"qid": "Q140", "proposal_ids": ["aaa"]})
    assert r.status_code == 401


def test_export_keeps_only_checked_ids(client, monkeypatch):
    from datetime import date

    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 24)

    monkeypatch.setattr("organon.api.routes.update.date", _FrozenDate)
    calls = _patch(monkeypatch, _diag_with_props())
    r = client.post(
        EXPORT_URL,
        json={"qid": "Q140", "taxon": "Panthera leo", "classification": "gbif",
              "proposal_ids": ["bbb"]},
    )
    assert r.status_code == 200
    assert r.json()["quickstatements"] == (
        'Q140\tP846\t"222"\tS248\tQ1531570\tS813\t+2026-09-24T00:00:00Z/11'
    )
    assert r.json()["retrieved"] == "2026-09-24"
    assert calls[0]["qid"] == "Q140"
    assert calls[0]["taxon"] == "Panthera leo"
    assert calls[0]["classification"] == "gbif"


def test_export_unknown_id_422(client, monkeypatch):
    _patch(monkeypatch, _diag_with_props())
    r = client.post(EXPORT_URL, json={"qid": "Q140", "proposal_ids": ["aaa", "zzz"]})
    assert r.status_code == 422
    assert "zzz" in str(r.json()["detail"])


def test_export_creation_without_qid(client, monkeypatch):

    from organon.core.update_diagnosis import Creation, Ecart, LigneCreation

    creation = Creation(
        id="ccc",
        label="Panthera leo",
        lignes=[LigneCreation(propriete="P31", valeur="Q16521", type="item")],
    )
    diag = DiagnosticResponse(
        qid=None,
        taxon="Panthera leo",
        ecarts=[
            Ecart(
                type="item_absent", severite="suggestion", propriete="P225", source="col",
                message="m", creation=creation,
            )
        ],
    )
    _patch(monkeypatch, diag)
    r = client.post(EXPORT_URL, json={"taxon": "Panthera leo", "proposal_ids": ["ccc"]})
    assert r.status_code == 200
    assert r.json()["quickstatements"] == 'CREATE\nLAST\tLmul\t"Panthera leo"\nLAST\tP31\tQ16521'


def test_export_proposal_without_qid_422(client, monkeypatch):
    _patch(monkeypatch, DiagnosticResponse(qid=None, taxon="x", ecarts=[]))
    r = client.post(EXPORT_URL, json={"taxon": "x", "proposal_ids": ["aaa"]})
    assert r.status_code == 422


def test_export_ids_required_non_empty(client):
    assert client.post(EXPORT_URL, json={"qid": "Q140", "proposal_ids": []}).status_code == 422
    assert client.post(EXPORT_URL, json={"proposal_ids": ["a"]}).status_code == 422


def test_export_ids_deduplicated(client, monkeypatch):
    _patch(monkeypatch, _diag_with_props())
    r = client.post(EXPORT_URL, json={"qid": "Q140", "proposal_ids": ["aaa", "aaa"]})
    assert r.json()["quickstatements"].count("\n") == 0


def test_export_diagnosis_errors_propagated(client, monkeypatch):
    _patch(monkeypatch, exc=TaxonNotFoundError("Q0"))
    assert client.post(EXPORT_URL, json={"qid": "Q0", "proposal_ids": ["a"]}).status_code == 404
    _patch(monkeypatch, exc=httpx.ConnectError("boom"))
    assert client.post(EXPORT_URL, json={"qid": "Q1", "proposal_ids": ["a"]}).status_code == 502


# --- article frwiki : service réel, réseau et génération simulés -------------------------------

FRWIKI_API = "https://fr.wikipedia.org/w/api.php"


def _wire_service(monkeypatch, sitelink):
    from organon.api.schemas import GenerateResponse, RankLine
    from organon.modules.wikidata.adapter import WikidataEntityAdapter

    def st(value):
        return {"mainsnak": {"datavalue": {"value": value}}, "rank": "normal"}

    entity = {"claims": {"P31": [st({"id": "Q16521"})], "P225": [st("Panthera leo")]}}
    if sitelink:
        entity["sitelinks"] = {"frwiki": {"title": sitelink}}

    class FakeWikidata(WikidataEntityAdapter):
        async def get_entity(self, qid):
            return entity

        async def get_entities(self, qids):
            return {}

    class FakeResolver:
        async def qids(self, taxon):
            return ["Q140"]

        async def taxon_qids(self, names):
            return {}

        async def aclose(self):
            pass

    async def generate(req):
        return GenerateResponse(
            requested_taxon="Panthera leo",
            resolved_taxon="Panthera leo",
            taxon_rank="espèce",
            wikitext="",
            taxobox_wikitext="",
            elapsed_seconds=0.0,
            used_classification="col",
            classification_taxobox="COL",
            used_domain="animal",
            rank_lines=[RankLine(rank="genre", name="Panthera", line="")],
        )

    monkeypatch.setattr(diagnosis, "WikidataEntityAdapter", FakeWikidata)
    monkeypatch.setattr(diagnosis, "WikidataSparqlAdapter", FakeResolver)
    monkeypatch.setattr("organon.api.routes.update._generate_core", generate)


def _frwiki_page(content):
    return httpx.Response(
        200,
        json={
            "query": {
                "pages": [
                    {
                        "title": "Lion",
                        "revisions": [
                            {
                                "revid": 7,
                                "timestamp": "2026-09-01T00:00:00Z",
                                "slots": {"main": {"content": content}},
                            }
                        ],
                    }
                ]
            }
        },
    )


@respx.mock
def test_response_contains_the_frwiki_gaps(client, monkeypatch):
    _wire_service(monkeypatch, "Lion")
    content = (
        "{{Taxobox début | animal | ''Panthera leo'' | | | classification=msw }}\n"
        "{{Taxobox | genre | Panthera }}\n"
        "{{Taxobox taxon | animal | espèce | Panthera leo | x }}\n{{Taxobox fin}}"
    )
    respx.get(FRWIKI_API).mock(return_value=_frwiki_page(content))
    r = client.post(URL, json={"taxon": "Panthera leo"})
    assert r.status_code == 200
    body = r.json()
    assert body["article_frwiki"]["titre"] == "Lion"
    (classification,) = [s for s in body["sections_frwiki"] if s["section"] == "classification"]
    assert [e["type"] for e in classification["ecarts"]] == ["taxobox_classification"]
    assert classification["ecarts"][0]["cible"] == "frwiki"
    assert all(e["cible"] == "wikidata" for e in body["ecarts"])


@respx.mock
def test_200_despite_frwiki_outage(client, monkeypatch):
    _wire_service(monkeypatch, "Lion")
    respx.get(FRWIKI_API).mock(side_effect=httpx.ConnectError("boom"))
    r = client.post(URL, json={"taxon": "Panthera leo"})
    assert r.status_code == 200
    assert r.json()["article_frwiki"] is None
    assert any("frwiki" in w for w in r.json()["avertissements"])


@respx.mock
def test_without_sitelink_frwiki_article_absent(client, monkeypatch):
    _wire_service(monkeypatch, None)
    r = client.post(URL, json={"taxon": "Panthera leo"})
    assert r.status_code == 200
    (article,) = [s for s in r.json()["sections_frwiki"] if s["section"] == "article"]
    assert [e["type"] for e in article["ecarts"]] == ["article_absent_frwiki"]


def test_domain_and_gbif_key_are_relayed_to_the_diagnosis(client, monkeypatch):
    calls = _patch(monkeypatch, DiagnosticResponse(qid="Q140", taxon="Panthera leo"))
    r = client.post(URL, json={"taxon": "Panthera leo", "domain": "animal", "gbif_key": 5219404})
    assert r.status_code == 200
    assert (calls[0]["domain"], calls[0]["gbif_key"]) == ("animal", 5219404)
