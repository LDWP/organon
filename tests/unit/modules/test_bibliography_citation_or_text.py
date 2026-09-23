"""Tests de `citation_or_text` : repli sur le texte brut hors DOI résolu."""

import httpx
import pytest

from organon.modules.bibliography import citation_or_text, extract_doi


def test_extract_doi_strips_trailing_punctuation():
    assert extract_doi("See (doi:10.1163/187529275X00239).") == "10.1163/187529275X00239"
    assert extract_doi("No identifier here.") is None


@pytest.mark.asyncio
async def test_resolved_doi_replaces_text():
    async def resolve(doi: str) -> str | None:
        return f"{{{{Article|doi={doi}}}}}"

    assert await citation_or_text(resolve, "A. 1975. doi:10.1234/x") == "{{Article|doi=10.1234/x}}"


@pytest.mark.asyncio
async def test_text_without_doi_is_unchanged_and_never_resolved():
    async def resolve(doi: str) -> str | None:
        raise AssertionError("must not be called")

    assert await citation_or_text(resolve, "Linnaeus 1758.") == "Linnaeus 1758."
    assert await citation_or_text(resolve, None) is None
    assert await citation_or_text(resolve, "") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [None, httpx.ConnectError("down"), ValueError("bad json")])
async def test_unresolved_or_failing_lookup_keeps_text(outcome):
    async def resolve(doi: str) -> str | None:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert await citation_or_text(resolve, "A. 1975. doi:10.1234/x") == "A. 1975. doi:10.1234/x"
