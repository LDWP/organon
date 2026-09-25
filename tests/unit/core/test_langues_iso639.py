"""Table des langues embarquée (organon/core/data/langues.yaml, générée depuis iso-639-3.tab du
SIL) : les valeurs attendues ci-dessous sont relevées dans la norme, pas dans le code."""

from __future__ import annotations

import pytest

from organon.core.langues import _charger, code_langue


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        ("swh", "sw"),
        ("npi", "ne"),
        ("zlm", "zlm"),
        ("yes", "yes"),
        ("nor", "no"),
        ("hbs", "sh"),
        ("sh", "sh"),
        ("cmn", "cmn"),
        ("zho", "zh"),
        ("Malay", "ms"),
        ("Nepali", "ne"),
        ("Swahili", "sw"),
        ("Greek", "el"),
        ("Modern Greek (1453-)", "el"),
        ("Cebuano", "ceb"),
        ("Hawaiian", "haw"),
    ],
)
def test_code_langue_suit_la_norme_sil(valeur, attendu):
    assert code_langue(valeur) == attendu


@pytest.mark.parametrize("valeur", ["zzz", "bih", "mul", "und", "zxx", "mis", "xx", "qaa"])
def test_code_hors_norme_ou_special_est_ecarte(valeur):
    assert code_langue(valeur) is None


def test_table_embarquee_conforme_a_la_norme_sil():
    langues = _charger()
    assert len(langues.vers_code) >= 7900
    assert len({c for c in langues.vers_code.values() if len(c) == 2}) == 184
    assert langues.vers_code["fre"] == langues.vers_code["fra"] == "fr"
    assert all(len(c) in (2, 3) for c in langues.vers_code.values())
    assert not {"mul", "und", "zxx", "mis"} & langues.vers_code.keys()
