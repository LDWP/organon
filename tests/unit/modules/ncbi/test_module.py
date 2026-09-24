"""Tests de NcbiModule : enrichissement seul (jamais de classification, NCBI Taxonomy
explicitement déconseillé comme référence — voir module.py), réutilise nom/rang déjà résolus."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.ncbi.module import NcbiModule


class FakeNcbiAdapter:
    def __init__(self, taxid: int | None):
        self._taxid = taxid

    async def search_taxid(self, name: str) -> int | None:
        return self._taxid


@pytest.mark.asyncio
async def test_collect_adds_link():
    module = NcbiModule(adapter=FakeNcbiAdapter(9823))
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa", rank="espèce"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["ncbi"] == {"id": 9823, "name": "Sus scrofa", "rank": "espèce"}

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{NCBI | 9823 | ''Sus scrofa'' | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=9823' "
        "target='_blank' rel='noopener noreferrer'>NCBI</a>"
    )


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = NcbiModule(adapter=FakeNcbiAdapter(9823))
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = NcbiModule(adapter=FakeNcbiAdapter(None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent():
    module = NcbiModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None
