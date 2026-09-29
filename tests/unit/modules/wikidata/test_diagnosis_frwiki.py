"""Diagnostic de l'article frwiki dans `diagnose_taxon` : lecture seule, panne frwiki = avertissement,
une seule génération partagée avec la partie Wikidata. Aucun réseau réel (respx + génération
injectée)."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from organon.api.schemas import GenerateResponse, RankLine
from organon.api.schemas import RankName
from organon.core.models import DistributionEntry
from organon.modules.wikidata.adapter import WikidataEntityAdapter
from organon.modules.wikidata.diagnosis import diagnose_taxon
from organon.modules.wikimedia.wikipedia.adapter import API_URL

LION_TAXOBOX = (
    Path(__file__).parents[2] / "core" / "fixtures" / "taxobox" / "Lion.txt"
).read_text(encoding="utf-8")


def _st(value):
    return {"mainsnak": {"datavalue": {"value": value}}, "rank": "normal"}


def _entity(sitelink):
    entity = {
        "claims": {
            "P31": [_st({"id": "Q16521"})],
            "P225": [_st("Panthera leo")],
        }
    }
    if sitelink:
        entity["sitelinks"] = {"frwiki": {"title": sitelink}}
    return entity


class FakeWikidata(WikidataEntityAdapter):
    def __init__(self, entity):
        super().__init__()
        self.entity = entity

    async def get_entity(self, qid):
        return self.entity

    async def get_entities(self, qids):
        return {}


class FakeResolver:
    async def qids(self, taxon):
        return ["Q140"]

    async def taxon_qids(self, names):
        return {}

    async def aclose(self):
        pass


def _response(**kw):
    base = dict(
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
    return GenerateResponse(**{**base, **kw})


async def _run(resp, sitelink="Lion"):
    calls = []

    async def generate(req):
        calls.append(req)
        return resp

    result = await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=generate,
        wikidata=FakeWikidata(_entity(sitelink)),
        resolver=FakeResolver(),
    )
    return result, calls


def _page(content, title="Lion", revid=42):
    return httpx.Response(
        200,
        json={
            "query": {
                "pages": [
                    {
                        "title": title,
                        "revisions": [
                            {
                                "revid": revid,
                                "timestamp": "2026-09-01T00:00:00Z",
                                "slots": {"main": {"content": content}},
                            }
                        ],
                    }
                ]
            }
        },
    )


def _sections(result):
    return {s.section: s for s in result.sections_frwiki}


@respx.mock
async def test_article_read_and_compared_without_touching_wikidata_gaps():
    respx.get(API_URL).mock(return_value=_page(LION_TAXOBOX))
    result, calls = await _run(_response())
    assert len(calls) == 1
    assert {e.cible for e in result.ecarts} == {"wikidata"}
    assert result.article_frwiki.titre == "Lion"
    assert result.article_frwiki.revid == 42
    assert result.article_frwiki.date == "2026-09-01T00:00:00Z"
    assert result.article_frwiki.url == "https://fr.wikipedia.org/wiki/Lion"
    classification = _sections(result)["classification"]
    assert {e.cible for e in classification.ecarts} == {"frwiki"}
    assert "taxobox_classification" in {e.type for e in classification.ecarts}


@respx.mock
async def test_iucn_compared_to_the_source_status():
    respx.get(API_URL).mock(return_value=_page(LION_TAXOBOX))
    result, _ = await _run(_response(iucn_status="EX", iucn_criterion="A1"))
    (gap,) = _sections(result)["uicn"].ecarts
    assert (gap.type, gap.valeur_wikidata, gap.valeur_source, gap.cible) == (
        "uicn_different",
        "VU A2c",
        "EX A1",
        "frwiki",
    )


@respx.mock
async def test_links_compared_to_the_exposed_see_also_block():
    respx.get(API_URL).mock(return_value=_page(LION_TAXOBOX + "\n== Liens externes ==\n"))
    expected = "== Liens externes ==\n{{Autres projets|commons=Panthera leo}}\n"
    result, _ = await _run(_response(see_also_wikitext=expected))
    links = _sections(result)["liens"]
    assert [e.type for e in links.ecarts] == ["projet_absent_article"]


@respx.mock
async def test_subtaxa_counted_and_truncation():
    article = LION_TAXOBOX + "\n== Liste des sous-espèces ==\n* ''Panthera leo leo''\n"
    respx.get(API_URL).mock(return_value=_page(article))
    subtaxa_list = [RankName(name="Panthera leo leo"), RankName(name="Panthera leo krugeri")]
    result, _ = await _run(_response(subtaxa=subtaxa_list, subtaxa_source="col"))
    section = _sections(result)["sous_taxons"]
    assert section.comptes["n_source"] == 2
    assert section.comptes["absents_article"] == ["Panthera leo krugeri"]

    result, _ = await _run(
        _response(subtaxa=subtaxa_list, subtaxa_source="col", truncated={"subtaxa": True})
    )
    section = _sections(result)["sous_taxons"]
    assert section.comptes is None and section.limites


@respx.mock
async def test_breakdown_marked_by_level_and_limits_without_hiding_anything():
    article = LION_TAXOBOX + "\n== Répartition ==\nLe lion vit en Inde.\n"
    respx.get(API_URL).mock(return_value=_page(article))
    entry = DistributionEntry(certain={"KE": "KE"})
    result, _ = await _run(_response(distribution_entries={"gbif": entry}))
    section = _sections(result)["repartition"]
    assert section.niveau == "prose"
    assert section.ecarts
    assert section.comptes["n_source"] == 1


@respx.mock
async def test_frwiki_outage_degrades_to_warning_without_exception():
    respx.get(API_URL).mock(side_effect=httpx.ConnectError("boom"))
    result, calls = await _run(_response())
    assert len(calls) == 1
    assert result.article_frwiki is None
    assert result.sections_frwiki == []
    assert any("frwiki" in w for w in result.avertissements)


@respx.mock
async def test_frwiki_page_not_found_warns():
    respx.get(API_URL).mock(return_value=httpx.Response(200, json={"query": {"pages": [{"missing": True}]}}))
    result, _ = await _run(_response())
    assert result.article_frwiki is None
    assert any("frwiki" in w for w in result.avertissements)


@respx.mock
async def test_without_frwiki_sitelink_reports_article_absent_without_frwiki_call():
    route = respx.get(API_URL)
    result, _ = await _run(_response(), sitelink=None)
    assert not route.called
    assert result.article_frwiki is None
    (gap,) = _sections(result)["article"].ecarts
    assert (gap.type, gap.severite, gap.cible) == ("article_absent_frwiki", "info", "frwiki")
