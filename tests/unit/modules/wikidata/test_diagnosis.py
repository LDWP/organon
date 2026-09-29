"""Service de diagnostic : résolution du QID, lecture de l'item, appel de la génération, assemblage.
Aucun réseau : adaptateurs et génération injectés."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from organon.api.schemas import GenerateResponse, RankLine, RankName
from organon.modules.wikidata.adapter import WikidataEntityAdapter
from organon.modules.wikidata.diagnosis import (
    AmbiguousTaxonError,
    TaxonNotFoundError,
    build_source_view,
    diagnose_taxon,
)
from organon.modules.wikimedia.wikidata.adapter import WikidataSparqlAdapter as QidAdapter


def _st(value, rank="normal", refs=True):
    s = {"mainsnak": {"datavalue": {"value": value}}, "rank": rank}
    if refs:
        s["references"] = [{"snaks": {"P248": [{"datavalue": {"value": {"id": "Q1"}}}]}}]
    return s


LION = {
    "claims": {
        "P31": [_st({"id": "Q16521"}, refs=False)],
        "P225": [_st("Panthera leo")],
        "P105": [_st({"id": "Q7432"}, refs=False)],
        "P171": [_st({"id": "Q127960"})],
        "P1420": [_st({"id": "Q900"})],
        "P815": [_st("183803", refs=False)],
        "P846": [_st("5219404", refs=False)],
        "P14607": [_st("777", refs=False)],
    }
}
PANTHERA = {"claims": {"P225": [_st("Panthera")]}}
SYNONYM = {"claims": {"P225": [_st("Felis leo")]}}


class FakeWikidata(WikidataEntityAdapter):
    def __init__(self, entities, fail_batch=False):
        super().__init__()
        self.entities = entities
        self.fail_batch = fail_batch

    async def get_entity(self, qid):
        return self.entities.get(qid)

    async def get_entities(self, qids):
        if self.fail_batch:
            raise httpx.ConnectError("boom")
        return {q: self.entities[q] for q in qids if q in self.entities}


class FakeResolver:
    def __init__(self, qids, batch=None, duplicates=None):
        self._qids = qids
        self._batch = batch or {}
        self._duplicates = duplicates or []
        self.id_queries = []

    async def items_by_external_ids(self, pairs):
        if isinstance(self._duplicates, Exception):
            raise self._duplicates
        self.id_queries.append(dict(pairs))
        return self._duplicates

    async def qids(self, taxon):
        return self._qids

    async def taxon_qids(self, names):
        if isinstance(self._batch, Exception):
            raise self._batch
        return {n: self._batch.get(n, []) for n in names}

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
        used_domain="animal",
        rank_lines=[RankLine(rank="genre", name="Panthera", line="")],
        synonyms=[RankName(name="Felis leo")],
        external_ids={"itis": "183803", "gbif": "5219404", "wrms": "1"},
    )
    return GenerateResponse(**{**base, **kw})


def _generate(resp):
    calls = []

    async def generate(req):
        calls.append(req)
        return resp

    generate.calls = calls
    return generate


ENTITIES = {"Q140": LION, "Q127960": PANTHERA, "Q900": SYNONYM}


async def test_nominal_diagnosis_only_reports_real_gaps():
    generate = _generate(_response())
    result = await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=generate,
        wikidata=FakeWikidata(ENTITIES),
        resolver=FakeResolver(["Q140"]),
    )
    assert result.qid == "Q140"
    assert result.source_reference == "col"
    # wrms connu de la source, absent de l'item ; le reste concorde (P225/P105/P171/P1420/ids).
    assert [(e.type, e.propriete) for e in result.ecarts] == [
        ("identifiant_absent_wikidata", "wrms")
    ]
    (gap,) = result.ecarts
    assert gap.severite == "suggestion"
    p = gap.proposition
    assert (p.module, p.propriete, p.valeur, p.type) == ("wrms", "P850", "1", "chaine")
    assert p.reference.stated_in == "Q604063"
    assert p.reference.retrieved == date.today()


async def test_missing_rank_proposal_uses_the_inverse_of_rank_qids():
    entity = {"claims": {k: v for k, v in LION["claims"].items() if k != "P105"}}
    result = await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=_generate(_response(external_ids={})),
        wikidata=FakeWikidata({**ENTITIES, "Q140": entity}),
        resolver=FakeResolver(["Q140"]),
    )
    (gap,) = result.ecarts
    assert (gap.type, gap.severite) == ("rang_absent_wikidata", "suggestion")
    assert (gap.proposition.propriete, gap.proposition.valeur) == ("P105", "Q7432")


async def test_missing_parent_gets_a_proposal_only_from_resolved_items():
    entity = {"claims": {k: v for k, v in LION["claims"].items() if k != "P171"}}
    kwargs = dict(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=_generate(_response(external_ids={})),
        wikidata=FakeWikidata({**ENTITIES, "Q140": entity}),
        resolver=FakeResolver(["Q140"]),
    )
    (gap,) = (await diagnose_taxon(**kwargs)).ecarts
    assert (gap.type, gap.severite, gap.proposition) == (
        "parent_absent_wikidata",
        "info",
        None,
    )
    kwargs["generate"] = _generate(_response(external_ids={}))
    result = await diagnose_taxon(**kwargs, resolved_items={"Panthera": "Q127960"})
    (gap,) = result.ecarts
    assert (gap.severite, gap.proposition.propriete, gap.proposition.valeur) == (
        "suggestion",
        "P171",
        "Q127960",
    )


async def test_unreferenced_statement_confirmed_by_source_becomes_a_suggestion():
    entity = {
        "claims": {**LION["claims"], "P225": [_st("Panthera leo", refs=False)]},
    }
    result = await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=_generate(_response(external_ids={})),
        wikidata=FakeWikidata({**ENTITIES, "Q140": entity}),
        resolver=FakeResolver(["Q140"]),
    )
    (gap,) = result.ecarts
    assert (gap.type, gap.severite, gap.propriete) == (
        "reference_manquante",
        "suggestion",
        "P225",
    )
    assert gap.proposition.valeur == "Panthera leo"


async def test_qid_given_skips_resolution_and_uses_p225_as_name():
    generate = _generate(_response())
    resolver = FakeResolver(["Q999"])  # ne doit pas être consulté
    result = await diagnose_taxon(
        taxon=None,
        qid="q140",
        classification="gbif",
        generate=generate,
        wikidata=FakeWikidata(ENTITIES),
        resolver=resolver,
    )
    assert result.qid == "Q140"
    assert generate.calls[0].taxon == "Panthera leo"
    assert generate.calls[0].classification == "gbif"


async def _absent(resolver=None, generate=None, taxon="Panthera leo", **kw):
    return await diagnose_taxon(
        taxon=taxon,
        qid=None,
        classification=None,
        generate=generate or _generate(_response()),
        wikidata=FakeWikidata({}),
        resolver=resolver or FakeResolver([], batch={"Panthera": ["Q127960"]}),
        **kw,
    )


async def test_absent_item_gets_a_creation_suggestion():
    resolver = FakeResolver([], batch={"Panthera": ["Q127960"]})
    result = await _absent(resolver)
    assert result.qid is None
    [gap] = result.ecarts
    assert (gap.type, gap.severite) == ("item_absent", "suggestion")
    rows = [(row.propriete, row.valeur) for row in gap.creation.lignes]
    assert ("P225", "Panthera leo") in rows
    assert ("P171", "Q127960") in rows
    assert ("P815", "183803") in rows
    assert resolver.id_queries == [{"P815": "183803", "P850": "1"}]


async def test_absent_item_found_through_an_external_id_is_a_possible_duplicate():
    result = await _absent(FakeResolver([], duplicates=["Q42"]))
    [gap] = result.ecarts
    assert (gap.type, gap.severite) == ("item_doublon_possible", "avertissement")
    assert "Q42" in gap.message
    assert gap.creation is None


async def test_absent_item_duplicate_check_failure_proposes_nothing():
    result = await _absent(FakeResolver([], duplicates=httpx.ConnectError("boom")))
    [gap] = result.ecarts
    assert (gap.type, gap.severite, gap.creation) == ("item_absent", "erreur", None)
    assert any("doublon" in w for w in result.avertissements)


async def test_absent_item_unknown_to_sources_stays_a_plain_error():
    async def generate(req):
        raise RuntimeError("taxon inconnu")

    result = await _absent(generate=generate)
    [gap] = result.ecarts
    assert (gap.type, gap.severite, gap.creation) == ("item_absent", "erreur", None)
    assert result.avertissements


async def test_absent_synonym_followed_by_source_is_not_created():
    result = await _absent(generate=_generate(_response(requested_taxon="Felis leo")))
    [gap] = result.ecarts
    assert (gap.type, gap.creation) == ("item_absent", None)


async def test_homonyms_raise_ambiguous_with_candidates():
    with pytest.raises(AmbiguousTaxonError) as exc:
        await diagnose_taxon(
            taxon="Morus",
            qid=None,
            classification=None,
            generate=_generate(_response()),
            wikidata=FakeWikidata({}),
            resolver=FakeResolver(["Q1", "Q2"]),
        )
    assert exc.value.candidates == ["Q1", "Q2"]


async def test_unknown_qid_raises_not_found():
    with pytest.raises(TaxonNotFoundError):
        await diagnose_taxon(
            taxon=None,
            qid="Q404",
            classification=None,
            generate=_generate(_response()),
            wikidata=FakeWikidata({}),
            resolver=FakeResolver([]),
        )


async def test_related_items_failure_degrades_to_warning():
    result = await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=_generate(_response()),
        wikidata=FakeWikidata(ENTITIES, fail_batch=True),
        resolver=FakeResolver(["Q140"]),
    )
    assert any("parents" in w or "synonymes" in w for w in result.avertissements)
    # sans noms de parents/synonymes résolus, aucun faux écart de parent n'est émis
    assert not [e for e in result.ecarts if e.type in ("parent_different", "parent_absent_wikidata")]


async def test_followed_synonym_reports_name_gap_only():
    resp = _response(resolved_taxon="Panthera leo", requested_taxon="Felis leo")
    result = await diagnose_taxon(
        taxon="Felis leo",
        qid=None,
        classification=None,
        generate=_generate(resp),
        wikidata=FakeWikidata({"Q1": {"claims": {"P31": [_st({"id": "Q16521"})], "P225": [_st("Felis leo")]}}}),
        resolver=FakeResolver(["Q1"]),
    )
    assert [e.type for e in result.ecarts] == ["nom_synonyme_source"]


def test_source_view_keeps_only_comparable_ids():
    resp = _response(external_ids={"itis": "1", "unknown_module": "x", "wfo": "w"})
    view = build_source_view(resp)
    assert view.external_ids == {"itis": "1", "wfo": "w"}
    assert view.parent_name == "Panthera"
    assert view.synonyms == ["Felis leo"]
    assert view.redirected_from is None


@respx.mock
async def test_qids_returns_all_homonym_items():
    respx.get("https://query.wikidata.org/sparql").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {"item": {"value": "http://www.wikidata.org/entity/Q1"}},
                        {"item": {"value": "http://www.wikidata.org/entity/Q2"}},
                    ]
                }
            },
        )
    )
    adapter = QidAdapter()
    try:
        assert await adapter.qids("Morus") == ["Q1", "Q2"]
        assert await adapter.qid("Morus") == "Q1"
    finally:
        await adapter.aclose()


def test_source_view_splits_gbif_legacy_key_and_col_xr_id():
    resp = _response(external_ids={"gbif": "65WK8", "gbif_key": "5786091"})
    assert build_source_view(resp).external_ids == {"gbif": "5786091", "gbif_col_xr": "65WK8"}


def test_source_view_digit_only_col_xr_id_is_not_taken_for_legacy_key():
    # Trimastix : id COL XR "8266" (chiffres seuls), clé legacy 4382180.
    resp = _response(external_ids={"gbif": "8266", "gbif_key": "4382180"})
    assert build_source_view(resp).external_ids == {"gbif": "4382180", "gbif_col_xr": "8266"}


def test_source_view_legacy_only_when_no_col_xr_link():
    resp = _response(external_ids={"gbif": "5219404", "gbif_key": "5219404"})
    assert build_source_view(resp).external_ids == {"gbif": "5219404"}


def test_source_view_ignores_gbif_id_without_legacy_key():
    resp = _response(external_ids={"gbif": "5TYZ9"})
    assert build_source_view(resp).external_ids == {}


async def test_gbif_col_xr_id_compared_to_p14607_and_legacy_key_to_p846():
    entity = {
        "claims": {
            "P31": [_st({"id": "Q16521"}, refs=False)],
            "P225": [_st("Trimastix")],
            "P846": [_st("4382180", refs=False)],
            "P14607": [_st("8266", refs=False)],
        }
    }
    resp = _response(
        requested_taxon="Trimastix",
        resolved_taxon="Trimastix",
        rank_lines=[],
        synonymes=[],
        external_ids={"gbif": "8266", "gbif_key": "4382180"},
    )
    result = await diagnose_taxon(
        taxon="Trimastix",
        qid=None,
        classification=None,
        generate=_generate(resp),
        wikidata=FakeWikidata({"Q1": entity}),
        resolver=FakeResolver(["Q1"]),
    )
    assert not [e for e in result.ecarts if e.propriete.startswith("gbif")]

    for prop in ("P846", "P14607"):
        entity["claims"].pop(prop)
    result = await diagnose_taxon(
        taxon="Trimastix",
        qid=None,
        classification=None,
        generate=_generate(resp),
        wikidata=FakeWikidata({"Q1": entity}),
        resolver=FakeResolver(["Q1"]),
    )
    proposals = {
        e.propriete: (e.proposition.propriete, e.proposition.valeur)
        for e in result.ecarts
        if e.propriete.startswith("gbif")
    }
    assert proposals == {"gbif": ("P846", "4382180"), "gbif_col_xr": ("P14607", "8266")}
    entity["claims"]["P846"] = [_st("4382180", refs=False)]
    entity["claims"]["P14607"] = [_st("ZZZ", refs=False)]
    result = await diagnose_taxon(
        taxon="Trimastix",
        qid=None,
        classification=None,
        generate=_generate(resp),
        wikidata=FakeWikidata({"Q1": entity}),
        resolver=FakeResolver(["Q1"]),
    )
    assert [(e.type, e.propriete) for e in result.ecarts if e.propriete.startswith("gbif")] == [
        ("identifiant_different", "gbif_col_xr")
    ]


def test_tpdb_and_eol_not_comparable():
    from organon.modules.wikidata.adapter import EXTERNAL_ID_PROPERTIES

    assert "tpdb" not in EXTERNAL_ID_PROPERTIES.values()
    assert "eol" not in EXTERNAL_ID_PROPERTIES.values()
    resp = _response(external_ids={"tpdb": "104204", "eol": "1", "itis": "2"})
    assert build_source_view(resp).external_ids == {"itis": "2"}


async def test_powo_lsid_on_wikidata_compared_to_bare_id():
    entity = {
        "claims": {
            "P31": [_st({"id": "Q16521"}, refs=False)],
            "P225": [_st("Quercus robur")],
            "P5037": [_st("urn:lsid:ipni.org:names:304293-2", refs=False)],
        }
    }
    resp = _response(
        requested_taxon="Quercus robur",
        resolved_taxon="Quercus robur",
        rank_lines=[],
        synonymes=[],
        external_ids={"powo": "304293-2"},
    )

    async def run(powo_source):
        resp2 = resp.model_copy(update={"external_ids": {"powo": powo_source}})
        return await diagnose_taxon(
            taxon="Quercus robur",
            qid=None,
            classification=None,
            generate=_generate(resp2),
            wikidata=FakeWikidata({"Q1": entity}),
            resolver=FakeResolver(["Q1"]),
        )

    assert not [e for e in (await run("304293-2")).ecarts if e.propriete == "powo"]
    entity["claims"].pop("P5037")
    (absent,) = [e for e in (await run("304293-2")).ecarts if e.propriete == "powo"]
    assert (absent.proposition.propriete, absent.proposition.valeur) == (
        "P5037",
        "urn:lsid:ipni.org:names:304293-2",
    )
    entity["claims"]["P5037"] = [_st("urn:lsid:ipni.org:names:304293-2", refs=False)]
    diffs = [e for e in (await run("999-1")).ecarts if e.propriete == "powo"]
    assert [(e.type, e.valeur_wikidata) for e in diffs] == [("identifiant_different", "304293-2")]


def _sparql_ok(*qids):
    return httpx.Response(
        200,
        json={
            "results": {
                "bindings": [
                    {"item": {"value": f"http://www.wikidata.org/entity/{q}"}} for q in qids
                ]
            }
        },
    )


@respx.mock
async def test_qids_retries_on_timeout_then_succeeds():
    route = respx.get("https://query.wikidata.org/sparql").mock(
        side_effect=[httpx.ReadTimeout("t"), _sparql_ok("Q140")]
    )
    adapter = QidAdapter()
    try:
        assert await adapter.qids("Panthera leo") == ["Q140"]
    finally:
        await adapter.aclose()
    assert route.call_count == 2


@respx.mock
async def test_qids_gives_up_after_three_timeouts():
    route = respx.get("https://query.wikidata.org/sparql").mock(
        side_effect=httpx.ReadTimeout("t")
    )
    adapter = QidAdapter()
    try:
        with pytest.raises(httpx.ReadTimeout):
            await adapter.qids("Gadus morhua")
    finally:
        await adapter.aclose()
    assert route.call_count == 3


async def test_qids_client_timeout_is_generous():
    adapter = QidAdapter()
    try:
        assert adapter._client.timeout.read == 30.0
    finally:
        await adapter.aclose()


@respx.mock
async def test_qids_query_accepts_all_taxon_classes():
    route = respx.get("https://query.wikidata.org/sparql").mock(return_value=_sparql_ok("Q1"))
    adapter = QidAdapter()
    try:
        await adapter.qids("Smilodon fatalis")
    finally:
        await adapter.aclose()
    query = route.calls[0].request.url.params["query"]
    for qid in ("Q16521", "Q310890", "Q23038290", "Q713623"):
        assert f"wd:{qid}" in query


def _sparql_pairs(*pairs):
    return httpx.Response(
        200,
        json={
            "results": {
                "bindings": [
                    {
                        "nom": {"value": nom},
                        "item": {"value": f"http://www.wikidata.org/entity/{q}"},
                    }
                    for nom, q in pairs
                ]
            }
        },
    )


async def _taxon_qids(names):
    adapter = QidAdapter()
    try:
        return await adapter.taxon_qids(names)
    finally:
        await adapter.aclose()


@respx.mock
async def test_taxon_qids_returns_zero_one_or_several_items_per_name():
    respx.get("https://query.wikidata.org/sparql").mock(
        return_value=_sparql_pairs(("Panthera", "Q127960"), ("Felis", "Q1"), ("Felis", "Q2"))
    )
    assert await _taxon_qids(["Panthera", "Felis", "Inconnu"]) == {
        "Panthera": ["Q127960"],
        "Felis": ["Q1", "Q2"],
        "Inconnu": [],
    }


@respx.mock
async def test_taxon_qids_single_query_with_escaped_names_and_taxon_classes():
    route = respx.get("https://query.wikidata.org/sparql").mock(return_value=_sparql_pairs())
    await _taxon_qids(['Abc "x"', "Def\\", "Ghi"])
    assert route.call_count == 1
    request = route.calls[0].request
    query = request.url.params["query"]
    assert '"Abc \\"x\\""' in query and '"Def\\\\"' in query and '"Ghi"' in query
    assert "wd:Q16521" in query and "wd:Q713623" in query
    assert "Organon" in request.headers["User-Agent"]


@respx.mock
async def test_taxon_qids_splits_batches_above_max_size():
    from organon.modules.wikimedia.wikidata.adapter import _BATCH_MAX

    route = respx.get("https://query.wikidata.org/sparql").mock(return_value=_sparql_pairs())
    names = [f"Taxon{i}" for i in range(_BATCH_MAX * 2 + 1)]
    result = await _taxon_qids(names + names[:3])  # doublons ignorés
    assert route.call_count == 3
    assert set(result) == set(names)


async def test_taxon_qids_empty_makes_no_request():
    assert await _taxon_qids([]) == {}


@respx.mock
async def test_taxon_qids_retries_once_then_raises():
    route = respx.get("https://query.wikidata.org/sparql").mock(
        side_effect=httpx.ReadTimeout("t")
    )
    with pytest.raises(httpx.ReadTimeout):
        await _taxon_qids(["Panthera"])
    assert route.call_count == 2


@respx.mock
async def test_taxon_qids_server_error_raises():
    respx.get("https://query.wikidata.org/sparql").mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await _taxon_qids(["Panthera"])


def _missing_parent_kwargs(resolver):
    entity = {"claims": {k: v for k, v in LION["claims"].items() if k != "P171"}}
    return dict(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=_generate(_response(external_ids={})),
        wikidata=FakeWikidata({**ENTITIES, "Q140": entity}),
        resolver=resolver,
    )


async def test_diagnose_resolves_parent_in_one_batch_and_proposes_it():
    resolver = FakeResolver(["Q140"], batch={"Panthera": ["Q127960"]})
    (gap,) = (await diagnose_taxon(**_missing_parent_kwargs(resolver))).ecarts
    assert (gap.severite, gap.proposition.propriete, gap.proposition.valeur) == (
        "suggestion",
        "P171",
        "Q127960",
    )


@pytest.mark.parametrize("found", [[], ["Q1", "Q2"]])
async def test_diagnose_zero_or_several_items_never_pick_one(found):
    resolver = FakeResolver(["Q140"], batch={"Panthera": found})
    (gap,) = (await diagnose_taxon(**_missing_parent_kwargs(resolver))).ecarts
    assert (gap.severite, gap.proposition) == ("info", None)


async def test_diagnose_batch_failure_degrades_to_warning_without_false_gap():
    resolver = FakeResolver(["Q140"], batch=httpx.ReadTimeout("t"))
    result = await diagnose_taxon(**_missing_parent_kwargs(resolver))
    assert any("ReadTimeout" in w for w in result.avertissements)
    assert all(e.proposition is None for e in result.ecarts)
    assert [e.type for e in result.ecarts] == ["parent_absent_wikidata"]


async def test_domain_and_gbif_key_are_passed_to_the_generation():
    generate = _generate(_response())
    await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification="col",
        domain="animal",
        gbif_key=5219404,
        generate=generate,
        wikidata=FakeWikidata(ENTITIES),
        resolver=FakeResolver(["Q140"]),
    )
    (req,) = generate.calls
    assert (req.taxon, req.classification, req.domain, req.gbif_key) == (
        "Panthera leo", "col", "animal", 5219404,
    )


async def test_default_generation_without_domain_or_gbif_key():
    generate = _generate(_response())
    await diagnose_taxon(
        taxon="Panthera leo",
        qid=None,
        classification=None,
        generate=generate,
        wikidata=FakeWikidata(ENTITIES),
        resolver=FakeResolver(["Q140"]),
    )
    (req,) = generate.calls
    assert (req.domain, req.gbif_key) == ("*", None)


@respx.mock
async def test_items_by_external_ids_single_query_on_property_value_pairs():
    route = respx.get("https://query.wikidata.org/sparql").mock(
        return_value=_sparql_pairs(("x", "Q42"), ("y", "Q42"), ("z", "Q43"))
    )
    resolver = QidAdapter()
    try:
        found = await resolver.items_by_external_ids({"P815": '18"3', "P846": "5219404"})
    finally:
        await resolver.aclose()
    assert found == ["Q42", "Q43"]
    query = route.calls[0].request.url.params["query"]
    assert '(wdt:P815 "18\\"3")' in query and '(wdt:P846 "5219404")' in query


async def test_items_by_external_ids_empty_makes_no_request():
    resolver = QidAdapter()
    try:
        assert await resolver.items_by_external_ids({}) == []
    finally:
        await resolver.aclose()


async def test_absent_synonym_is_created_linked_to_its_unique_accepted_item():
    resolver = FakeResolver([], batch={"Panthera leo": ["Q140"]})
    result = await _absent(
        resolver, generate=_generate(_response(requested_taxon="Felis leo")), taxon="Felis leo"
    )
    [gap] = result.ecarts
    assert (gap.type, gap.severite) == ("item_absent", "suggestion")
    assert gap.creation.label == "Felis leo"
    assert [(li.propriete, li.valeur) for li in gap.creation.lignes] == [
        ("P31", "Q16521"), ("P225", "Felis leo"), ("P1420", "Q140")
    ]
    assert gap.creation.rattachements[0].qid == "Q140"
    assert resolver.id_queries == []  # les ids de la source sont ceux du taxon accepté


async def test_absent_synonym_with_unresolved_or_ambiguous_accepted_item_not_created():
    for batch in ({}, {"Panthera leo": ["Q1", "Q2"]}):
        resolver = FakeResolver([], batch=batch)
        result = await _absent(
        resolver, generate=_generate(_response(requested_taxon="Felis leo")), taxon="Felis leo"
    )
        [gap] = result.ecarts
        assert gap.creation is None


async def test_existing_item_missing_synonym_without_item_proposes_creation():
    resolver = FakeResolver(["Q140"], batch={"Panthera": ["Q127960"], "Felis x": ["Q1", "Q2"]})
    result = await diagnose_taxon(
        taxon="Panthera leo", qid=None, classification=None,
        generate=_generate(
            _response(synonyms=[RankName(name="Felis leo"), RankName(name="Felis nova"),
                                 RankName(name="Felis x")])
        ),
        wikidata=FakeWikidata(ENTITIES), resolver=resolver,
    )
    by_name = {e.valeur_source: e for e in result.ecarts if e.type == "synonyme_absent_wikidata"}
    assert by_name["Felis nova"].creation.rattachements[0].qid == "Q140"
    assert by_name["Felis x"].creation is None  # homonymes : jamais de choix arbitraire
    assert "Felis leo" not in by_name


async def test_existing_item_uicn_status_proposed():
    resolver = FakeResolver(["Q140"], batch={"Panthera": ["Q127960"]})
    result = await diagnose_taxon(
        taxon="Panthera leo", qid=None, classification=None,
        generate=_generate(_response(iucn_status="VU")),
        wikidata=FakeWikidata(ENTITIES), resolver=resolver,
    )
    gap = next(e for e in result.ecarts if e.type == "uicn_absent_wikidata")
    assert gap.proposition.valeur == "Q278113"


async def test_absent_item_generation_network_failure_logged_as_warning(caplog):
    async def generate(req):
        raise httpx.ReadTimeout("timed out")

    with caplog.at_level("WARNING"):
        await _absent(generate=generate)
    [record] = caplog.records
    assert record.levelname == "WARNING"
    assert record.exc_info is None


async def test_absent_item_generation_bug_logged_with_traceback(caplog):
    async def generate(req):
        raise RuntimeError("bug interne")

    with caplog.at_level("WARNING"):
        await _absent(generate=generate)
    [record] = caplog.records
    assert record.levelname == "ERROR"
    assert record.exc_info is not None
