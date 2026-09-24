"""Tests de IucnModule : module d'enrichissement seul (pas de classification), qui ne retient
que l'évaluation de périmètre Global la plus récente parmi les évaluations d'un taxon."""

from __future__ import annotations

import pytest

from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.iucn.module import IucnModule

PANTHERA_LEO_RESPONSE = {
    "taxon": {"sis_id": 15951, "scientific_name": "Panthera leo", "authority": "(Linnaeus, 1758)"},
    "assessments": [
        {
            "latest": False,
            "scopes": [{"code": "1"}],
            "red_list_category_code": "VU",
            "criteria": "A2abcd",
            "url": "https://www.iucnredlist.org/species/15951/107265605",
        },
        {
            "latest": True,
            "scopes": [{"code": "1"}],
            "red_list_category_code": "VU",
            "criteria": "A2abcd",
            "url": "https://www.iucnredlist.org/species/15951/226503991",
        },
        {
            # Périmètre Europe, "latest" dans son propre périmètre mais pas Global : ignoré.
            "latest": True,
            "scopes": [{"code": "3"}],
            "red_list_category_code": "RE",
            "criteria": "",
            "url": "https://www.iucnredlist.org/species/15951/45140239",
        },
    ],
}


class FakeIucnAdapter:
    def __init__(self, response: dict | None):
        self._response = response

    async def scientific_name(self, genus_name, species_name, infra_name=None):
        return self._response


@pytest.mark.asyncio
async def test_collect_retains_latest_global_assessment():
    module = IucnModule(adapter=FakeIucnAdapter(PANTHERA_LEO_RESPONSE))
    # rang déjà résolu par le module de classification en amont dans le pipeline réel (IUCN ne
    # classe jamais, voir test_collect_never_classifies) : nécessaire ici pour wp_apply_italics.
    struct = Struct(taxon=TaxonInfo(name="Panthera leo", rank="espèce"), kingdom="animal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is not None
    data = result.links["iucn"]
    assert data["id"] == 15951
    assert data["risk"] == "VU"
    assert data["criterion"] == "A2abcd"
    assert data["url"] == "https://www.iucnredlist.org/species/15951/226503991"

    bioref = module.render_bioref(result)
    assert bioref.startswith("{{UICN | 15951 | ''Panthera leo'' (Linnaeus, 1758) | consulté le=")
    assert module.debug_link(result) == (
        "<a href='https://www.iucnredlist.org/species/15951/226503991' target='_blank' "
        "rel='noopener noreferrer'>UICN</a>"
    )


@pytest.mark.asyncio
async def test_collect_returns_none_when_never_evaluated():
    module = IucnModule(adapter=FakeIucnAdapter(None))
    struct = Struct(taxon=TaxonInfo(name="Nonexistentgenusxyz zzz"))

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result is None


@pytest.mark.asyncio
async def test_collect_never_classifies():
    module = IucnModule(adapter=FakeIucnAdapter(PANTHERA_LEO_RESPONSE))
    struct = Struct(taxon=TaxonInfo(name="Panthera leo"))

    result = await module.collect(struct, is_classification=True, options=GenerateOptions())

    assert result is None


def test_render_bioref_absent_without_id():
    module = IucnModule()
    struct = Struct(taxon=TaxonInfo(name="X"))
    assert module.render_bioref(struct) is None


def test_debug_link_absent_without_url():
    module = IucnModule()
    struct = Struct(
        taxon=TaxonInfo(name="X"), links={"iucn": {"id": 1, "name": "X", "url": None}}
    )
    assert module.debug_link(struct) is None


@pytest.mark.asyncio
async def test_author_html_entity_decoded():
    response = {
        "taxon": {
            "sis_id": 215053597,
            "scientific_name": "Columellia oblonga",
            "authority": "Ruiz &amp; Pav.",
        },
        "assessments": [
            {
                "latest": True,
                "scopes": [{"code": "1"}],
                "red_list_category_code": "LC",
                "criteria": "",
                "url": "https://www.iucnredlist.org/species/215053597/1",
            }
        ],
    }
    module = IucnModule(adapter=FakeIucnAdapter(response))
    struct = Struct(taxon=TaxonInfo(name="Columellia oblonga", rank="espèce"), kingdom="végétal")

    result = await module.collect(struct, is_classification=False, options=GenerateOptions())

    assert result.links["iucn"]["author"] == "Ruiz & Pav."
    assert "&amp;" not in module.render_bioref(result)
