from organon.api.routes.generate import _compute_external_ids
from organon.core.models import Struct, TaxonInfo


def test_gbif_exposes_legacy_key_next_to_id():
    struct = Struct(taxon=TaxonInfo(name="x"), links={"gbif": {"id": "65WK8", "key": 5786091}})
    assert _compute_external_ids(struct, ["gbif"]) == {"gbif": "65WK8", "gbif_key": "5786091"}


def test_other_modules_unchanged():
    struct = Struct(taxon=TaxonInfo(name="x"), links={"itis": {"id": 1, "key": 2}})
    assert _compute_external_ids(struct, ["itis"]) == {"itis": "1"}
