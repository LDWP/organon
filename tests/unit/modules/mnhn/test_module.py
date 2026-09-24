"""Tests de MnhnModule : limité aux rangs espèce/genre (seules fiches dédiées existant sur le
site), slug construit avec un séparateur `/` entre les mots (voir module.py, ancien bug `/_`)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.mnhn.module import MnhnModule


class FakeMnhnAdapter:
    def __init__(self, existing_paths: set[str]):
        self._existing_paths = existing_paths

    async def exists(self, path: str) -> bool:
        return path in self._existing_paths


@pytest.mark.asyncio
async def test_collect_species_builds_slash_separated_slug():
    module = MnhnModule(adapter=FakeMnhnAdapter({"species/gadus/morhua"}))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua", rank="espèce"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["mnhn"] == {
        "id": "gadus/morhua",
        "rank": "espèce",
        "url": "https://science.mnhn.fr/taxon/species/gadus/morhua",
    }

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{MNHN | espèce | gadus/morhua | ''Gadus morhua'' | consulté le="
    )
    assert module.debug_link(result) == (
        "<a href='https://science.mnhn.fr/taxon/species/gadus/morhua' target='_blank' "
        "rel='noopener noreferrer'>MNHN</a>"
    )


@pytest.mark.asyncio
async def test_collect_genus():
    module = MnhnModule(adapter=FakeMnhnAdapter({"genus/gadus"}))
    struct = Struct(taxon=TaxonInfo(name="Gadus", rank="genre"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["mnhn"]["id"] == "gadus"


@pytest.mark.asyncio
async def test_collect_returns_none_for_unsupported_rank():
    module = MnhnModule(adapter=FakeMnhnAdapter({"family/gadidae"}))
    struct = Struct(taxon=TaxonInfo(name="Gadidae", rank="famille"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = MnhnModule(adapter=FakeMnhnAdapter({"species/gadus/morhua"}))
    struct = Struct(taxon=TaxonInfo(name="Gadus morhua", rank="espèce"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_not_found():
    module = MnhnModule(adapter=FakeMnhnAdapter(set()))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz", rank="espèce"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
