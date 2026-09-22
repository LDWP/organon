"""Zoologist surnames carrying a particle ("De Haan") resolve against the table, which stores them
without it ("Haan")."""

import pytest

from organon.core.models import Struct, TaxonInfo
from organon.core.rendering.authors import resolve_main_author


def _author(author: str) -> str:
    struct = Struct(taxon=TaxonInfo(name="Sus scrofa", rank="espèce", author=author), kingdom="animal")
    return resolve_main_author(struct)[0]


@pytest.mark.parametrize("token", ["Haan", "De Haan", "de Haan", "van Haan", "d'Haan"])
def test_particle_is_ignored_when_looking_up_zoologist(token):
    assert _author(token).startswith(f"[[Willem de Haan|{token}]]")


def test_unknown_surname_with_particle_stays_unlinked():
    assert "Willem" not in _author("De Unknownsurname")
