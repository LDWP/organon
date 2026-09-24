"""Tests de AdwModule : enrichissement seul, citation formatée façon Wikipédia (auteur seul,
"X et Y", "X et al." à partir de 3 auteurs — voir module.py)."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.adw.adapter import AdwCitation, Author
from organon.modules.adw.module import AdwModule


class FakeAdwAdapter:
    def __init__(self, citation: AdwCitation | None):
        self._citation = citation

    async def fetch(self, slug: str) -> AdwCitation | None:
        return self._citation


LINNAEUS = Author(nom="Linnaeus", prenom1="C", prenom2=".")


@pytest.mark.asyncio
async def test_collect_single_author():
    module = AdwModule(
        adapter=FakeAdwAdapter(AdwCitation(premier_auteur=LINNAEUS, annee="1758"))
    )
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa", rank="espèce"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["adw"] == {"id": "Sus_scrofa", "citation": "Linnaeus, C.", "date": "1758"}

    bioref = module.render_bioref(result)
    assert bioref.startswith(
        "{{ADW | Sus_scrofa | ''Sus scrofa'' | consulté le="
    )
    assert "auteur=Linnaeus, C." in bioref
    assert "date=1758" in bioref
    assert module.debug_link(result) == (
        "<a href='https://animaldiversity.org/accounts/Sus_scrofa/' target='_blank' "
        "rel='noopener noreferrer'>ADW</a>"
    )


@pytest.mark.asyncio
async def test_collect_two_authors():
    other_author = Author(nom="Smith", prenom1="J")
    module = AdwModule(
        adapter=FakeAdwAdapter(AdwCitation(premier_auteur=LINNAEUS, autres_auteurs=[other_author]))
    )
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["adw"]["citation"] == "Linnaeus, C. et Smith, J"


@pytest.mark.asyncio
async def test_collect_three_or_more_authors_uses_et_al():
    other_authors = [Author(nom="Smith", prenom1="J"), Author(nom="Doe", prenom1="A")]
    module = AdwModule(
        adapter=FakeAdwAdapter(AdwCitation(premier_auteur=LINNAEUS, autres_auteurs=other_authors))
    )
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert "et al." in result.links["adw"]["citation"]


@pytest.mark.asyncio
async def test_collect_page_without_citation():
    module = AdwModule(adapter=FakeAdwAdapter(AdwCitation(premier_auteur=None)))
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["adw"] == {"id": "Sus_scrofa"}


@pytest.mark.asyncio
async def test_collect_not_found():
    module = AdwModule(adapter=FakeAdwAdapter(None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = AdwModule(adapter=FakeAdwAdapter(AdwCitation(premier_auteur=LINNAEUS)))
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None
