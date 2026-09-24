"""Le site n'a de fiche dédiée que pour le nom binomial espèce (`/Genus/species`) : un taxon à
un seul mot (genre ou famille) n'a qu'un formulaire de recherche, insuffisant pour classifier
(voir module.py) mais suffisant pour confirmer sa présence et publier une citation
{{ReptileDB genre}}/{{ReptileDB famille}}. Ces tests verrouillent que `collect()` ne déclenche
cette branche que lorsque le rang a déjà été résolu par un autre module de classification
(`struct.taxon.rang` déjà "genre"/"famille" à l'entrée, jamais deviné depuis le nom)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.core.rendering.support import retrieval_dates
from organon.modules.reptile_database.adapter import SpeciesHit
from organon.modules.reptile_database.module import ReptileDatabaseModule

CDATE = retrieval_dates()
"""`render_bioref` appelle `retrieval_dates()` sans argument (date du jour) : recalculée ici à
l'identique plutôt que figée en dur, pour ne pas casser ces tests le jour suivant leur écriture."""


@dataclass
class FakeAdapter:
    species_hit: SpeciesHit | None = None
    genus_present: bool = False
    family_present: bool = False

    async def get_species(self, genus: str, species: str) -> SpeciesHit | None:
        return self.species_hit

    async def genus_exists(self, genus: str) -> bool:
        return self.genus_present

    async def family_exists(self, family: str) -> bool:
        return self.family_present


@pytest.mark.asyncio
async def test_collect_species_classification_unchanged():
    hit = SpeciesHit(
        nom="Varanus komodoensis", auteur="OUWENS, 1912", famille="Varanidae", ordre="Squamata"
    )
    module = ReptileDatabaseModule(adapter=FakeAdapter(species_hit=hit))
    struct = Struct(taxon=TaxonInfo(name="Varanus komodoensis"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is not None
    assert result.taxon.rank == "espèce"
    assert result.classification == "reptiledb"
    assert [r.name for r in result.ranks] == ["Varanus", "Varanidae", "Squamata"]
    assert module.render_bioref(result) == (
        f"{{{{ReptileDB espèce | Varanus | komodoensis | OUWENS, 1912 | consulté le={CDATE} }}}}"
    )


@pytest.mark.asyncio
async def test_collect_genus_adds_citation_when_rank_already_resolved():
    module = ReptileDatabaseModule(adapter=FakeAdapter(genus_present=True))
    struct = Struct(taxon=TaxonInfo(name="Varanus", rank="genre"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["reptile_database"] == {"rank": "genre", "name": "Varanus"}
    assert module.render_bioref(result) == (
        f"{{{{ReptileDB genre | Varanus | consulté le={CDATE} }}}}"
    )
    assert module.debug_link(result) == (
        "<a href='https://reptile-database.reptarium.cz/advanced_search?genus=Varanus"
        "&exact%5B%5D=genus&ok=Search&do=AdvancedSearchForm-submit' target='_blank' "
        "rel='noopener noreferrer'>Reptile Database</a>"
    )


@pytest.mark.asyncio
async def test_collect_family_adds_citation_when_rank_already_resolved():
    module = ReptileDatabaseModule(adapter=FakeAdapter(family_present=True))
    struct = Struct(taxon=TaxonInfo(name="Varanidae", rank="famille"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    assert result.links["reptile_database"] == {"rank": "famille", "name": "Varanidae"}
    assert module.render_bioref(result) == (
        f"{{{{ReptileDB famille | Varanidae | consulté le={CDATE} }}}}"
    )


@pytest.mark.asyncio
async def test_collect_genus_returns_none_when_absent_from_database():
    module = ReptileDatabaseModule(adapter=FakeAdapter(genus_present=False))
    struct = Struct(taxon=TaxonInfo(name="Notagenusxyz", rank="genre"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_ignores_single_word_taxon_during_classification():
    """Aucune fiche genre/famille sur le site (voir module.py) : pas de hiérarchie parente
    extractible, donc ce module ne peut jamais servir de source de classification à ces rangs
    — seulement y ajouter une citation une fois le rang déjà résolu par un autre module."""
    module = ReptileDatabaseModule(adapter=FakeAdapter(genus_present=True))
    struct = Struct(taxon=TaxonInfo(name="Varanus"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_ignores_single_word_taxon_at_unsupported_rank():
    module = ReptileDatabaseModule(adapter=FakeAdapter(genus_present=True))
    struct = Struct(taxon=TaxonInfo(name="Squamata", rank="ordre"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None
