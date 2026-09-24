"""Non-régression pour le repli de résolution COL XR (audit GBIF/COL XR) : `type=EXACT` côté
ChecklistBank ne reconnaît ni la notation de sous-genre entre parenthèses ("Mus (Mus) musculus"
pour la requête "Mus musculus") ni un changement d'accord de genre latin sur l'épithète
("Macrovipera lebetina" vs "lebetinus"). Voir `organon.modules.col_xr.lookup`."""

from __future__ import annotations

from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.lookup import (
    _latin_gender_variants,
    _strip_subgenus,
    find_col_xr_link,
    resolve_col_xr_matches,
)


def _entry(
    id_: str,
    scientific_name: str,
    *,
    status: str = "accepted",
    rank: str = "species",
    kingdom: str = "Animalia",
    accepted: dict | None = None,
) -> dict:
    usage: dict = {"status": status, "name": {"scientificName": scientific_name, "rank": rank}}
    if accepted is not None:
        usage["accepted"] = accepted
    return {
        "id": id_,
        "usage": usage,
        "classification": [{"id": "k1", "rank": "kingdom", "name": kingdom}],
    }


class FakeColXrAdapter(ColXrAdapter):
    """Simule les réponses ChecklistBank observées lors de l'audit, indexées par
    (texte de requête, `exact`) — pas de véritable appel HTTP."""

    def __init__(self, responses: dict[tuple[str, bool], list[dict]]) -> None:
        super().__init__()
        self._responses = responses
        self.calls: list[tuple[str, bool]] = []

    async def search(self, taxon: str, *, exact: bool = True) -> list[dict]:
        self.calls.append((taxon, exact))
        return self._responses.get((taxon, exact), [])


def test_strip_subgenus_removes_the_parenthesized_token() -> None:
    assert _strip_subgenus("Mus (Mus) musculus") == "Mus musculus"
    assert _strip_subgenus("Mus musculus") == "Mus musculus"


def test_latin_gender_variants_generates_the_two_other_endings() -> None:
    assert _latin_gender_variants("Macrovipera lebetina") == [
        "Macrovipera lebetinus",
        "Macrovipera lebetinum",
    ]
    assert _latin_gender_variants("Macrovipera lebetinus") == [
        "Macrovipera lebetina",
        "Macrovipera lebetinum",
    ]


def test_latin_gender_variants_name_without_recognized_ending() -> None:
    assert _latin_gender_variants("Panthera tigris") == []


async def test_resolve_mus_musculus_finds_the_record_with_subgenus() -> None:
    accepted = _entry("mus-1", "Mus (Mus) musculus")
    adapter = FakeColXrAdapter(
        {
            ("Mus musculus", True): [],
            ("Mus musculus", False): [accepted],
        }
    )

    candidates = await resolve_col_xr_matches(adapter, "Mus musculus")

    assert candidates == [accepted]


async def test_resolve_plasmodium_falciparum_finds_the_record_with_subgenus() -> None:
    accepted = _entry("plas-1", "Plasmodium (Laverania) falciparum", kingdom="Protozoa")
    adapter = FakeColXrAdapter(
        {
            ("Plasmodium falciparum", True): [],
            ("Plasmodium falciparum", False): [accepted],
        }
    )

    candidates = await resolve_col_xr_matches(adapter, "Plasmodium falciparum")

    assert candidates == [accepted]


async def test_resolve_drosophila_melanogaster_adds_accepted_record_to_exact_synonym() -> None:
    accepted = _entry("droso-accepted", "Drosophila (Sophophora) melanogaster")
    synonym = _entry(
        "droso-synonym",
        "Drosophila melanogaster",
        status="synonym",
        accepted={
            "id": "droso-accepted",
            "name": {"scientificName": "Drosophila (Sophophora) melanogaster"},
        },
    )
    adapter = FakeColXrAdapter(
        {
            ("Drosophila melanogaster", True): [synonym],
            ("Drosophila melanogaster", False): [synonym, accepted],
        }
    )

    candidates = await resolve_col_xr_matches(adapter, "Drosophila melanogaster")

    assert synonym in candidates
    assert accepted in candidates
    assert any(r["usage"]["status"] == "accepted" for r in candidates)


async def test_resolve_macrovipera_lebetina_retries_with_latin_gender_agreement() -> None:
    accepted = _entry("macro-1", "Macrovipera lebetinus")
    adapter = FakeColXrAdapter(
        {
            ("Macrovipera lebetina", True): [],
            ("Macrovipera lebetina", False): [],
            ("Macrovipera lebetinus", False): [accepted],
        }
    )

    candidates = await resolve_col_xr_matches(adapter, "Macrovipera lebetina")

    assert candidates == [accepted]
    # Repli de dernier recours seulement : le sous-genre est tenté avant le genre latin.
    assert ("Macrovipera lebetina", False) in adapter.calls
    assert ("Macrovipera lebetinus", False) in adapter.calls


async def test_resolve_taxon_absent_triggers_no_false_positive() -> None:
    adapter = FakeColXrAdapter({})

    candidates = await resolve_col_xr_matches(adapter, "Nonexistus fakus")

    assert candidates == []


async def test_find_col_xr_link_benefits_from_the_subgenus_fallback() -> None:
    accepted = _entry("mus-1", "Mus (Mus) musculus", rank="species")
    adapter = FakeColXrAdapter(
        {
            ("Mus musculus", True): [],
            ("Mus musculus", False): [accepted],
        }
    )

    info = await find_col_xr_link(adapter, "Mus musculus", "animal")

    assert info is not None
    assert info.id == "mus-1"
    assert info.nom == "Mus (Mus) musculus"
