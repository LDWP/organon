"""Tests for `wp_apply_italics`."""

import pytest

from organon.core.rendering.grammar import wp_apply_italics


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "Pseudechiniscus (Pseudechiniscus) papillosus",
            "''Pseudechiniscus (Pseudechiniscus) papillosus''",
        ),
        ("Homo sapiens", "''Homo sapiens''"),
        ("Rosa canina var. alba", "''Rosa canina ''var.'' alba''"),
    ],
)
def test_species_italics(name, expected):
    """A subgenus in parentheses stays inside one italic run."""
    assert wp_apply_italics(name, "espèce", "animal") == expected


def test_subgenus_link_form():
    """The linked form wraps the whole name in a single pair."""
    result = wp_apply_italics(
        "Pseudechiniscus (Pseudechiniscus)", "sous-genre", "animal", link=True
    )
    assert result == "''[[Pseudechiniscus (Pseudechiniscus)]]''"
