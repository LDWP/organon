"""The "Taxobox UICN" template drops its criterion parameter when the source gives none."""

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, TaxonInfo
from organon.core.rendering.sections import render_taxobox


def _struct(rank: str, iucn: dict) -> Struct:
    return Struct(
        taxon=TaxonInfo(name="Panthera leo", rank=rank),
        kingdom="animal",
        ranks=[RankName(name="Panthera", rank="genre")],
        links={"iucn": iucn},
    )


def _iucn_line(struct: Struct) -> str:
    lines = render_taxobox(struct, GenerateOptions(), []).splitlines()
    return next(line for line in lines if line.startswith("{{Taxobox UICN"))


def test_missing_criterion_leaves_no_empty_parameter():
    assert _iucn_line(_struct("espèce", {"risk": "LC"})) == "{{Taxobox UICN | LC }}"


def test_empty_criterion_leaves_no_empty_parameter():
    assert _iucn_line(_struct("espèce", {"risk": "LC", "criterion": ""})) == "{{Taxobox UICN | LC }}"


def test_criterion_is_kept_when_given():
    line = _iucn_line(_struct("espèce", {"risk": "VU", "criterion": "A2cd"}))
    assert line == "{{Taxobox UICN | VU | A2cd }}"


def test_no_iucn_template_above_species():
    taxobox = render_taxobox(_struct("genre", {"risk": "LC"}), GenerateOptions(), [])
    assert "Taxobox UICN" not in taxobox
