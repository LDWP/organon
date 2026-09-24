"""Tests de TelametroModule : enrichissement botanique seul, ne retient que le hit BDTFX dont
`scientific_name` correspond exactement, auteur+année concaténés, noms communs groupés par
statut dans `struct.other_names` (voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.telametro.module import TelametroModule


class FakeTelametroAdapter:
    def __init__(self, hits: list[dict], common_names: dict[str, list[str]] | None = None):
        self._hits = hits
        self._common_names = common_names or {}

    async def search(self, name: str) -> list[dict]:
        return self._hits

    async def french_common_names(self, nomenclatural_number: int) -> dict[str, list[str]]:
        return self._common_names


@pytest.mark.asyncio
async def test_collect_adds_link_with_author_and_year():
    hits = [
        {
            "bdtfx": {
                "scientific_name": "Quercus robur",
                "nomenclatural_number": 65635,
                "author": "L.",
                "year": "1753",
            }
        }
    ]
    module = TelametroModule(
        adapter=FakeTelametroAdapter(hits, {"nom vernaculaire": ["Chêne pédonculé"]})
    )
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"), kingdom="vegetal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["telametro"] == {
        "id": 65635,
        "name": "Quercus robur",
        "author": "L. 1753",
    }
    assert result.other_names["Tela-métro"] == {"nom vernaculaire": ["Chêne pédonculé"]}

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{Tela-métro | 65635 | ''Quercus robur'' L. 1753 | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://www.tela-botanica.org/eflore/?referentiel=bdtfx&module=fiche"
        "&action=fiche&num_nom=65635&onglet=synthese' target='_blank' "
        "rel='noopener noreferrer'>TelaMétro</a>"
    )


@pytest.mark.asyncio
async def test_collect_ignores_hits_without_bdtfx_or_non_exact_name():
    hits = [
        {"bdtfx": None},
        {"bdtfx": {"scientific_name": "Quercus petraea", "nomenclatural_number": 1}},
    ]
    module = TelametroModule(adapter=FakeTelametroAdapter(hits))
    struct = Struct(taxon=TaxonInfo(name="Quercus robur"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    hits = [{"bdtfx": {"scientific_name": "X", "nomenclatural_number": 1}}]
    module = TelametroModule(adapter=FakeTelametroAdapter(hits))
    struct = Struct(taxon=TaxonInfo(name="X"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = TelametroModule(adapter=FakeTelametroAdapter([]))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
