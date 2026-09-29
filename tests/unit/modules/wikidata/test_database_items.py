import re

from organon.modules.wikidata.adapter import DATABASE_ITEMS, EXTERNAL_ID_PROPERTIES

GBIF_COL_XR = "gbif_col_xr"


def test_every_comparable_module_has_a_database_item():
    comparable = set(EXTERNAL_ID_PROPERTIES.values()) | {GBIF_COL_XR}
    assert set(DATABASE_ITEMS) == comparable


def test_qids_have_the_expected_form():
    for module, qid in DATABASE_ITEMS.items():
        assert re.fullmatch(r"Q\d+", qid), module
