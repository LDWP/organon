"""Tests de GbifModule : classification acceptée, absence de résultat, et statut synonyme en
mode enrichissement (pas de suivi de redirection). Double léger de GbifAdapter/ColXrAdapter
plutôt que respx : de nombreux endpoints distincts sont appelés par un seul `collect()`."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.gbif.module import GbifModule


class FakeColXrAdapter(ColXrAdapter):
    """Aucune fiche COL XR ne correspond : GbifModule garde son identifiant numérique."""

    def __init__(self) -> None:
        pass

    async def search(self, name: str, exact: bool = True) -> list[dict]:
        return []


class FakeGbifAdapter:
    def __init__(self, search_results: list[dict], name_infos: dict[int, dict]):
        self._search_results = search_results
        self._name_infos = name_infos

    async def search(self, name: str) -> list[dict]:
        return self._search_results

    async def name_info(self, key: int) -> dict | None:
        return self._name_infos.get(key)

    async def species_profiles(self, key: int) -> list[dict]:
        return []

    async def species_record(self, key: int) -> dict | None:
        return None

    async def children_page(self, key: int, offset: int = 0) -> dict:
        return {"results": [], "endOfRecords": True}

    async def vernacular_names_page(self, key: int, offset: int = 0) -> dict:
        return {"results": [], "endOfRecords": True}

    async def synonyms_page(self, key: int, offset: int = 0) -> dict:
        return {"results": [], "endOfRecords": True}

    async def taxref_related(self, key: int) -> list[dict]:
        return []

    doi_citations: dict[str, str] = {}

    async def resolve_doi_citation(self, doi: str) -> str | None:
        return self.doi_citations.get(doi)


APIS_RECORD = {
    "key": 1341976,
    "kingdom": "Animalia",
    "family": "Apidae",
    "genus": "Apis",
    "canonicalName": "Apis mellifera",
    "rank": "SPECIES",
    "taxonomicStatus": "ACCEPTED",
    "publishedIn": None,
    "numDescendants": 0,
}
APIS_NAME_INFO = {
    "canonicalNameComplete": "Apis mellifera Linnaeus, 1758",
    "canonicalName": "Apis mellifera",
    "rank": "SPECIES",
}


@pytest.mark.asyncio
async def test_collect_classification_accepted_species():
    module = GbifModule(
        adapter=FakeGbifAdapter([APIS_RECORD], {1341976: APIS_NAME_INFO}),
        col_xr_adapter=FakeColXrAdapter(),
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"), kingdom="animal")

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "GBIF"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Linnaeus, 1758"
    assert result.kingdom == "animal"
    assert result.links["gbif"]["id"] == 1341976
    assert result.links["gbif"]["detected_status"] == "accepté"
    # "kingdom" alimente struct.kingdom (voir ci-dessus), pas struct.ranks.
    assert {r.name for r in result.ranks} == {"Apidae", "Apis"}

    bioref = module.render_bioref(result)
    prefix = "{{GBIF | 1341976 | ''Apis mellifera'' Linnaeus, 1758 | consulté le="
    assert bioref == [prefix + bioref[0].rsplit("=", 1)[1]]
    assert module.debug_link(result) == (
        "<a href='https://www.gbif.org/species/1341976' target='_blank' "
        "rel='noopener noreferrer'>GBIF</a>"
    )


@pytest.mark.asyncio
async def test_collect_not_found():
    module = GbifModule(adapter=FakeGbifAdapter([], {}), col_xr_adapter=FakeColXrAdapter())
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_synonym_enrichment_does_not_redirect():
    record = {
        **APIS_RECORD,
        "key": 1000001,
        "acceptedKey": 1341976,
        "taxonomicStatus": "SYNONYM",
    }
    module = GbifModule(
        adapter=FakeGbifAdapter([record], {1000001: APIS_NAME_INFO}),
        col_xr_adapter=FakeColXrAdapter(),
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifica"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["gbif"]["detected_status"] == "synonyme"
    assert result.links["gbif"]["synonym"] is True
    assert result.classification == ""


@pytest.mark.asyncio
async def test_collect_exposes_legacy_key_next_to_col_xr_id(monkeypatch):
    from organon.modules.col_xr.lookup import ColXrLinkInfo

    async def fake_link(adapter, name, domain):
        return ColXrLinkInfo(id="8266", nom="Apis mellifera", auteur=None, rang="espèce", eteint=None)

    monkeypatch.setattr("organon.modules.gbif.module.find_col_xr_link", fake_link)
    module = GbifModule(
        adapter=FakeGbifAdapter([APIS_RECORD], {1341976: APIS_NAME_INFO}),
        col_xr_adapter=FakeColXrAdapter(),
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"), kingdom="animal")

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.links["gbif"]["id"] == "8266"
    assert result.links["gbif"]["key"] == 1341976


@pytest.mark.asyncio
async def test_collect_legacy_key_without_col_xr():
    module = GbifModule(
        adapter=FakeGbifAdapter([APIS_RECORD], {1341976: APIS_NAME_INFO}),
        col_xr_adapter=FakeColXrAdapter(),
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"), kingdom="animal")
    result = await module.collect(struct, is_classification=True, options=GenerateOptions())
    assert result is not None
    assert result.links["gbif"]["key"] == result.links["gbif"]["id"] == 1341976


@pytest.mark.asyncio
async def test_vernacular_grouped_by_language_keeps_names_without_language_and_inpn_stays_french():
    class Adapter(FakeGbifAdapter):
        async def vernacular_names_page(self, key: int, offset: int = 0) -> dict:
            return {
                "results": [
                    {"language": "fra", "vernacularName": "Abeille", "source": "TAXREF"},
                    {"language": "eng", "vernacularName": "Honey bee", "source": "X"},
                    {"language": "", "vernacularName": "Apis", "source": "X"},
                    {"vernacularName": "Sans langue"},
                ],
                "endOfRecords": True,
            }

    module = GbifModule(
        adapter=Adapter([APIS_RECORD], {1341976: APIS_NAME_INFO}),
        col_xr_adapter=FakeColXrAdapter(),
    )
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"), kingdom="animal")

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result.vernacular["GBIF"] == {
        "fr": ["Abeille"],
        "en": ["Honey bee"],
        "und": ["Apis", "Sans langue"],
    }
    assert result.vernacular["INPN"] == {"fr": ["Abeille"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("published_in", "expected"),
    [
        (
            "Poinar 1975. https://doi.org/10.1163/187529275X00239",
            "{{Article | titre=T | périodique=P | date=1975}}",
        ),
        ("Linnaeus 1758. Systema naturae.", "Linnaeus 1758. Systema naturae."),
        (
            "Poinar 1975. https://doi.org/10.1234/unknown",
            "Poinar 1975. https://doi.org/10.1234/unknown",
        ),
    ],
)
async def test_collect_original_publication_resolves_doi(published_in, expected):
    adapter = FakeGbifAdapter(
        [{**APIS_RECORD, "publishedIn": published_in}], {1341976: APIS_NAME_INFO}
    )
    adapter.doi_citations = {
        "10.1163/187529275X00239": "{{Article | titre=T | périodique=P | date=1975}}"
    }
    module = GbifModule(adapter=adapter, col_xr_adapter=FakeColXrAdapter())
    struct = Struct(taxon=TaxonInfo(name="Apis mellifera"), kingdom="animal")

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.original_publication == expected
