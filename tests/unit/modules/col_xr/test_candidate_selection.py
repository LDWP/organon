"""Competing "accepted" ChecklistBank records for one exact name (Escherichia coli, Toxoplasma
gondii) must be arbitrated: kingdom, then curated over auto-merged, then coherent nomenclatural
code, then API order."""

from __future__ import annotations

import pytest

from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.lookup import (
    find_col_xr_link,
    resolve_col_xr_concept_id,
    select_col_xr_candidate,
)


def _record(
    id_: str,
    *,
    kingdom: str = "Animalia",
    domain: str | None = None,
    merged: bool | None = None,
    code: str | None = None,
    name: str = "Toxoplasma gondii",
) -> dict:
    usage_name: dict = {"scientificName": name, "rank": "species"}
    if code is not None:
        usage_name["code"] = code
    usage: dict = {"status": "accepted", "name": usage_name}
    if merged is not None:
        usage["merged"] = merged
    classification = [{"id": "k", "rank": "kingdom", "name": kingdom}]
    if domain is not None:
        classification.insert(0, {"id": "d", "rank": "domain", "name": domain})
    return {"id": id_, "usage": usage, "classification": classification}


class _FakeAdapter(ColXrAdapter):
    def __init__(self, results: list[dict]) -> None:
        super().__init__()
        self._results = results

    async def search(self, taxon: str, *, exact: bool = True) -> list[dict]:
        return self._results


def _ids(record: dict | None) -> str | None:
    return record["id"] if record else None


def test_empty_candidates_return_none():
    assert select_col_xr_candidate([], "animal") is None


def test_known_domain_restricts_to_matching_kingdom():
    plant = _record("PLANT", kingdom="Plantae", merged=False)
    animal = _record("ANIMAL", kingdom="Animalia", merged=True)
    assert _ids(select_col_xr_candidate([plant, animal], "animal")) == "ANIMAL"


def test_unknown_domain_does_not_restrict():
    plant = _record("PLANT", kingdom="Plantae")
    animal = _record("ANIMAL", kingdom="Animalia")
    assert _ids(select_col_xr_candidate([plant, animal], "*")) == "PLANT"


def test_domain_without_any_match_keeps_all_candidates():
    plant = _record("PLANT", kingdom="Plantae")
    assert _ids(select_col_xr_candidate([plant], "animal")) == "PLANT"


def test_curated_record_wins_over_auto_merged_one():
    merged = _record("MERGED", merged=True)
    curated = _record("CURATED", merged=False)
    assert _ids(select_col_xr_candidate([merged, curated], "animal")) == "CURATED"


def test_missing_merged_flag_counts_as_curated():
    merged = _record("MERGED", merged=True)
    unflagged = _record("UNFLAGGED")
    assert _ids(select_col_xr_candidate([merged, unflagged], "animal")) == "UNFLAGGED"


@pytest.mark.parametrize(
    ("bad", "good"),
    [
        # Toxoplasma gondii: botanical code on an Animalia record.
        (_record("BAD", merged=True, code="botanical"), _record("GOOD", merged=True, code="zoological")),
        # Escherichia coli: botanical code on a Bacteria record.
        (
            _record("BAD", kingdom="Bacteria", domain="Bacteria", merged=True, code="botanical"),
            _record("GOOD", kingdom="Bacteria", domain="Bacteria", merged=True, code="bacterial"),
        ),
        # Zoological code on a Fungi record.
        (_record("BAD", kingdom="Fungi", merged=True, code="zoological"), _record("GOOD", kingdom="Fungi", merged=True, code="botanical")),
        # Bacterial code on a eukaryote.
        (_record("BAD", domain="Eukaryota", merged=True, code="bacterial"), _record("GOOD", domain="Eukaryota", merged=True, code="zoological")),
    ],
)
def test_inconsistent_nomenclatural_code_is_dropped_when_merged_flag_ties(bad, good):
    assert _ids(select_col_xr_candidate([bad, good], "*")) == "GOOD"


def test_api_order_decides_when_nothing_else_does():
    first = _record("FIRST", merged=False, code="zoological")
    second = _record("SECOND", merged=False, code="zoological")
    assert _ids(select_col_xr_candidate([first, second], "animal")) == "FIRST"


@pytest.mark.asyncio
async def test_find_link_picks_curated_record_among_competing_accepted():
    adapter = _FakeAdapter([_record("MERGED", merged=True), _record("CURATED", merged=False)])
    link = await find_col_xr_link(adapter, "Toxoplasma gondii", "animal")
    assert link is not None and link.id == "CURATED"


@pytest.mark.asyncio
async def test_concept_id_picks_coherent_record_among_competing_accepted():
    adapter = _FakeAdapter(
        [
            _record("BAD", merged=True, code="botanical"),
            _record("GOOD", merged=True, code="zoological"),
        ]
    )
    assert await resolve_col_xr_concept_id(adapter, "Toxoplasma gondii", "animal") == "GOOD"
