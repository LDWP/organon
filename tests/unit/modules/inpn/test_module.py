"""Tests de InpnModule : classification via résolution ancêtre par ancêtre du fil d'Ariane
(voir module.py), noms vernaculaires français, et notation "Genre (Sous-genre)" (TAXREF
n'indexe le sous-genre que sous son seul lbNom)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.inpn.adapter import InpnAdapter
from organon.modules.inpn.module import InpnModule

_BREADCRUMB_HTML = (
    '<a href="/taxref-web/taxa/0">Biota</a> &rsaquo; '
    '<a href="/taxref-web/taxa/1">Animalia</a> &rsaquo; '
    '<a href="/taxref-web/taxa/2">Chordata</a> &rsaquo; '
    '<a href="/taxref-web/taxa/3">Mammalia</a> &rsaquo; '
    '<a href="/taxref-web/taxa/4">Carnivora</a> &rsaquo; '
    '<a href="/taxref-web/taxa/5">Canidae</a> &rsaquo; '
    '<a href="/taxref-web/taxa/6">Vulpes</a> &rsaquo;'
)
_VERNACULAR_HTML = (
    "<legend>NOMS VERNACULAIRES</legend>"
    '<span>Renard roux, Renard</span> (<a href="#">Français</a>)'
    "</fieldset>"
)
_DETAIL_HTML = _BREADCRUMB_HTML + _VERNACULAR_HTML

_VULPES_VULPES = {
    "cdNom": 60585,
    "lbNom": "Vulpes vulpes",
    "validite": "NR",
    "rang": {"rang": "ES"},
    "lbAuteur": "Linnaeus, 1758",
}
_ANCESTORS = {
    "Animalia": [{"cdNom": 1, "lbNom": "Animalia", "validite": "NR", "rang": {"rang": "KD"}}],
    "Chordata": [{"cdNom": 2, "lbNom": "Chordata", "validite": "NR", "rang": {"rang": "PH"}}],
    "Mammalia": [{"cdNom": 3, "lbNom": "Mammalia", "validite": "NR", "rang": {"rang": "CL"}}],
    "Carnivora": [{"cdNom": 4, "lbNom": "Carnivora", "validite": "NR", "rang": {"rang": "OR"}}],
    "Canidae": [{"cdNom": 5, "lbNom": "Canidae", "validite": "NR", "rang": {"rang": "FM"}}],
    "Vulpes": [{"cdNom": 6, "lbNom": "Vulpes", "validite": "NR", "rang": {"rang": "GN"}}],
}


class FakeInpnAdapter(InpnAdapter):
    """Hérite de InpnAdapter pour réutiliser parse_breadcrumb/parse_vernacular_french tels
    quels (méthodes statiques, pures) ; seuls search()/detail_html() (réseau) sont doublés."""

    def __init__(self, search_results: dict[str, list[dict]], html_page: str = ""):
        self._search_results = search_results
        self._html_page = html_page

    async def search(self, full_name: str, max_rows: int = 500) -> list[dict]:
        return self._search_results.get(full_name, [])

    async def detail_html(self, cd_nom: int) -> str:
        return self._html_page


@pytest.mark.asyncio
async def test_collect_classification_resolves_ancestors_and_kingdom():
    results = {"Vulpes vulpes": [_VULPES_VULPES], **_ANCESTORS}
    module = InpnModule(adapter=FakeInpnAdapter(results, _DETAIL_HTML))
    struct = Struct(taxon=TaxonInfo(name="Vulpes vulpes"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.classification == "TAXREF"
    assert result.taxon.rank == "espèce"
    assert result.taxon.author == "Linnaeus, 1758"
    assert result.kingdom == "animal"
    rank_names = ["Vulpes", "Canidae", "Carnivora", "Mammalia", "Chordata"]
    assert [r.name for r in result.ranks] == rank_names
    assert result.vernacular["INPN"] == {"fr": ["Renard roux", "Renard"]}
    assert result.links["inpn"]["id"] == 60585

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{INPN | 60585 | ''Vulpes vulpes'' Linnaeus, 1758 | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://taxref.mnhn.fr/taxref-web/taxa/60585' target='_blank' "
        "rel='noopener noreferrer'>INPN</a>"
    )


@pytest.mark.asyncio
async def test_collect_enrichment_only_skips_ancestor_resolution():
    results = {"Vulpes vulpes": [_VULPES_VULPES]}
    module = InpnModule(adapter=FakeInpnAdapter(results, _VERNACULAR_HTML))
    struct = Struct(taxon=TaxonInfo(name="Vulpes vulpes"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.classification == ""
    assert result.links["inpn"]["id"] == 60585
    assert result.vernacular["INPN"] == {"fr": ["Renard roux", "Renard"]}


@pytest.mark.asyncio
async def test_collect_subgenus_notation_searches_by_subgenus_name_only():
    # TAXREF stocke "Eupelmus (Eupelmus)" sous son seul lbNom "Eupelmus", rang SSGN — voir
    # docstring de module.py.
    record = {
        "cdNom": 999,
        "lbNom": "Eupelmus",
        "validite": "NR",
        "rang": {"rang": "SSGN"},
    }
    module = InpnModule(adapter=FakeInpnAdapter({"Eupelmus": [record]}, ""))
    struct = Struct(taxon=TaxonInfo(name="Eupelmus (Eupelmus)"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["inpn"]["id"] == 999


@pytest.mark.asyncio
async def test_collect_not_found():
    module = InpnModule(adapter=FakeInpnAdapter({}))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_ignores_non_reference_names():
    record = {**_VULPES_VULPES, "validite": "SYN"}
    module = InpnModule(adapter=FakeInpnAdapter({"Vulpes vulpes": [record]}))
    struct = Struct(taxon=TaxonInfo(name="Vulpes vulpes"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


async def test_adapter_identifies_itself_honestly():
    import respx

    from organon.core.http import USER_AGENT

    with respx.mock(assert_all_called=False) as router:
        route = router.get(url__startswith="https://taxref.mnhn.fr/").respond(200, json=[])
        async with InpnAdapter() as adapter:
            await adapter.search("Vulpes vulpes")
    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT
