"""Snapshot guard: the wikitext and the API response produced for
six mocked taxa (animal, plant, bacterium, bird, fungus, virus) must stay identical to `snapshots/`.

Regenerate on purpose: `ORGANON_UPDATE_SNAPSHOTS=1 pytest tests/unit/core/rendering/
test_render_snapshot.py`."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from organon.api.routes.generate import _assemble_response, _select_main_author
from organon.api.schemas import GenerateRequest
from organon.core.config import GenerateOptions
from organon.core.models import (
    Basionym,
    DistributionEntry,
    Etymology,
    RankName,
    Struct,
    SubTaxonList,
    SynonymList,
    TaxonInfo,
    TypeTaxon,
)
from organon.core.rendering.engine import render
from organon.core.rendering.support import retrieval_dates
from organon.modules.bootstrap import ensure_modules_registered

SNAPSHOTS = Path(__file__).parent / "snapshots"


def _animal() -> tuple[Struct, str]:
    struct = Struct(
        taxon=TaxonInfo(name="Panthera leo", rank="espèce", author="(Linnaeus, 1758)"),
        classification="gbif",
        classification_taxobox="biologique",
        kingdom="animal",
        ranks=[
            RankName(name="Panthera", rank="genre", author="Oken, 1816"),
            RankName(name="Felidae", rank="famille", author="G. Fischer, 1817"),
            RankName(name="Carnivora", rank="ordre"),
            RankName(name="Mammalia", rank="classe"),
            RankName(name="Chordata", rank="embranchement"),
        ],
        subtaxa=SubTaxonList(
            items=[
                RankName(name="Panthera leo leo", rank="sous-espèce", author="(Linnaeus, 1758)"),
                RankName(
                    name="Panthera leo melanochaita", rank="sous-espèce", author="(Smith, 1842)"
                ),
            ],
            source="gbif",
            truncated=True,
        ),
        synonyms=SynonymList(
            items=[
                RankName(name="Felis leo", rank="espèce", author="Linnaeus, 1758"),
                RankName(name="Leo leo", rank="espèce", extinct=False),
            ],
            source="gbif",
        ),
        basionym=Basionym(name="Felis leo", author="Linnaeus, 1758", source="gbif"),
        type_taxon=TypeTaxon(name="Panthera leo", rank="espèce", source="gbif"),
        etymology=Etymology(text="Du latin leo, « lion ».", source="gbif"),
        original_publication="Linnaeus, C. (1758). Systema Naturae.",
        vernacular={"gbif": {"fr": ["Lion", "Lion d'Afrique"], "en": ["Lion"], "und": ["Leo"]}},
        other_names={"telametro": {"Recommandé ou typique": ["Lion royal"]}},
        distribution={"gbif": DistributionEntry(certain={"KE": "KE"}, uncertain={"TZ": "TZ"})},
        habitat="terrestre",
        links={
            "gbif": {
                "id": "5219404",
                "key": 5219404,
                "name": "Panthera leo",
                "author": "(Linnaeus, 1758)",
            },
            "iucn": {
                "id": "15951",
                "name": "Panthera leo",
                "url": "https://iucnredlist.org/15951",
                "risk": "VU",
                "criterion": "A2abcd",
            },
            "cites": {
                "name": "Panthera leo",
                "appendix": "II",
                "date": "2019",
                "precision": "population",
            },
            "wrms": {
                "id": "1",
                "name": "Panthera leo",
                "author": "(Linnaeus, 1758)",
                "extinct": False,
            },
        },
    )
    return struct, "gbif"


def _plante() -> tuple[Struct, str]:
    struct = Struct(
        taxon=TaxonInfo(name="Quercus robur", rank="espèce", author="L."),
        classification="powo",
        classification_taxobox="biologique",
        kingdom="plante",
        ranks=[
            RankName(name="Quercus", rank="genre", author="L."),
            RankName(name="Fagaceae", rank="famille", author="Dumort."),
            RankName(name="Fagales", rank="ordre"),
            RankName(name="Magnoliopsida", rank="classe"),
        ],
        synonyms=SynonymList(
            items=[RankName(name="Quercus pedunculata", rank="espèce", author="Ehrh.")],
            source="powo",
        ),
        vernacular={"telametro": {"fr": ["Chêne pédonculé", "Chêne commun"]}},
        distribution={
            "powo": DistributionEntry(
                certain={"FRA": "FRA"}, uncertain={"ITA": "ITA"}, introduced={"CAN": "CAN"}
            )
        },
        habitat="terrestre",
        links={
            "powo": {"id": "295374-1", "name": "Quercus robur", "author": "L."},
            "ipni": {"id": "295374-1", "name": "Quercus robur", "author": "L."},
            "iucn": {
                "id": "63532",
                "name": "Quercus robur",
                "url": "https://iucnredlist.org/63532",
                "risk": "LC",
            },
        },
    )
    return struct, "powo"


def _bacterie() -> tuple[Struct, str]:
    struct = Struct(
        taxon=TaxonInfo(
            name="Escherichia coli",
            rank="espèce",
            author="(Migula 1895) Castellani & Chalmers 1919",
        ),
        classification="lpsn",
        classification_taxobox="biologique",
        kingdom="bactérie",
        domain="Bacteria",
        ranks=[
            RankName(name="Escherichia", rank="genre", author="Castellani & Chalmers 1919"),
            RankName(name="Enterobacteriaceae", rank="famille"),
            RankName(name="Enterobacterales", rank="ordre"),
            RankName(name="Gammaproteobacteria", rank="classe"),
            RankName(name="Pseudomonadota", rank="embranchement"),
        ],
        basionym=Basionym(name="Bacillus coli", author="Migula 1895", source="lpsn"),
        etymology=Etymology(text="Du nom de Theodor Escherich.", source="lpsn"),
        habitat=None,
        links={
            "lpsn": {
                "id": "escherichia-coli",
                "name": "Escherichia coli",
                "rank": "espèce",
                "url": "https://lpsn.dsmz.de/species/escherichia-coli",
                "author": "(Migula 1895) Castellani & Chalmers 1919",
            },
            "ncbi": {"id": "562", "name": "Escherichia coli", "rank": "espèce"},
        },
    )
    return struct, "lpsn"


def _oiseau() -> tuple[Struct, str]:
    struct = Struct(
        taxon=TaxonInfo(name="Turdus merula", rank="espèce", author="Linnaeus, 1758"),
        classification="coi_ioc",
        classification_taxobox="biologique",
        kingdom="oiseau",
        ranks=[
            RankName(name="Turdus", rank="genre", author="Linnaeus, 1758"),
            RankName(name="Turdidae", rank="famille", author="Rafinesque, 1815"),
            RankName(name="Passeriformes", rank="ordre"),
            RankName(name="Aves", rank="classe"),
            RankName(name="Chordata", rank="embranchement"),
        ],
        vernacular={"coi_ioc": {"fr": ["Merle noir"]}},
        habitat="terrestre",
        links={
            "coi_ioc": {
                "id": "turdus-merula",
                "name": "Turdus merula",
                "rank": "espèce",
                "author": "Linnaeus, 1758",
                "family": "Turdidae",
            },
        },
    )
    return struct, "coi_ioc"


def _champignon() -> tuple[Struct, str]:
    struct = Struct(
        taxon=TaxonInfo(name="Amanita muscaria", rank="espèce", author="(L.) Lam."),
        classification="indexfungorum",
        classification_taxobox="biologique",
        kingdom="champignon",
        ranks=[
            RankName(name="Amanita", rank="genre", author="Pers."),
            RankName(name="Amanitaceae", rank="famille", author="R.Heim"),
            RankName(name="Agaricales", rank="ordre"),
            RankName(name="Agaricomycetes", rank="classe"),
            RankName(name="Basidiomycota", rank="division"),
        ],
        basionym=Basionym(name="Agaricus muscarius", author="L.", source="indexfungorum"),
        vernacular={"telametro": {"fr": ["Amanite tue-mouches"]}},
        habitat="terrestre",
        links={
            "indexfungorum": {
                "id": "190449",
                "name": "Amanita muscaria",
                "rank": "espèce",
                "author": "(L.) Lam.",
            },
        },
    )
    return struct, "indexfungorum"


def _virus() -> tuple[Struct, str]:
    struct = Struct(
        taxon=TaxonInfo(name="Betacoronavirus pandemicum", rank="espèce"),
        classification="ICTV",
        classification_taxobox="ICTV",
        kingdom="virus",
        ranks=[
            RankName(name="Betacoronavirus", rank="genre"),
            RankName(name="Orthocoronavirinae", rank="sous-famille"),
            RankName(name="Coronaviridae", rank="famille"),
            RankName(name="Nidovirales", rank="ordre"),
            RankName(name="Pisoniviricetes", rank="classe"),
        ],
        links={
            "ictv": {"id": "202201234", "name": "Betacoronavirus pandemicum", "rank": "espèce"},
        },
    )
    return struct, "ictv"


CASES = {"animal": _animal, "plante": _plante, "bacterie": _bacterie,
    "oiseau": _oiseau,
    "champignon": _champignon,
    "virus": _virus,
}


def _check(name: str, produced: str) -> None:
    produced = produced.replace(retrieval_dates(), "<DATE>")
    path = SNAPSHOTS / name
    if os.environ.get("ORGANON_UPDATE_SNAPSHOTS"):
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(produced, encoding="utf-8", newline="\n")
    assert produced == path.read_text(encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _modules():
    ensure_modules_registered()


@pytest.mark.parametrize("case", CASES)
def test_wikitext_snapshot(case):
    struct, _ = CASES[case]()
    struct.taxon.resolved_author = struct.taxon.author
    struct.links["footer"] = {"portals": ["biologie"], "categories": ["Catégorie test"]}
    _check(f"{case}.wikitext", render(struct, GenerateOptions()))


@pytest.mark.parametrize("case", CASES)
def test_api_response_snapshot(case):
    struct, classification_id = CASES[case]()
    req = GenerateRequest(taxon=struct.taxon.name)
    candidates = _select_main_author(struct, GenerateOptions(), classification_id)
    response = _assemble_response(
        req,
        GenerateOptions(),
        classification_id,
        struct,
        [classification_id, *(m for m in struct.links if m != classification_id)],
        [],
        [],
        0.0,
        candidates,
    )
    data = response.model_dump(mode="json")
    data["elapsed_seconds"] = 0
    _check(
        f"{case}.api.json", json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
