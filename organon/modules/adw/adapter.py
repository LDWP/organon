"""Network access to Animal Diversity Web (animaldiversity.org).

HTML scraping, no API: one possible page per taxon
(`accounts/<Name_with_underscores>/`). The author and year are not
exposed in a structured form: only the "To cite this page:" paragraph
gives a textual version, extracted by regular expression (1, 2 or 3+
authors).

The "taxon not found" marker is a `<h1>Page not found</h1>` in an HTTP
200 body. Some valid taxa (e.g. *Bufo bufo*) redirect (302) to a
"classification" subpage with no citation of its own;
`follow_redirects=True` still recognizes them as found, without a
citation.

The citation is cut by a nested `<span>` holding the access date, which
the site never renders itself (a literal `{%B %d, %Y}`): it is ignored,
only the publication year in the citation text is kept.

The search for the following authors is bounded to the text AFTER the
first author found: applied to the whole citation, the regex could
capture "and" as a bogus author (e.g. "Wund, M. and P. Myers 2005.").
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

import httpx

from organon.core.http import OwnedClientMixin, fetch_text

BASE_URL = "https://animaldiversity.org"

_NOT_FOUND_RE = re.compile(r"<h1>\s*Page not found\s*</h1>")
_CITATION_BLOCK_RE = re.compile(
    r'To cite this page:(?P<texte>.*?)<span[^>]*data-slot="accessed-date"', re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")

_LETTERS = r"[^\W\d_]+"
_FIRST_AUTHOR_RE = re.compile(rf"(?P<nom>{_LETTERS}),\s(?P<prenom1>[A-Z]\.)(?P<prenom2> [A-Z]\.)?")
_OTHER_AUTHOR_RE = re.compile(
    rf"(and )?(?P<prenom1>[A-Z]\.)(?P<prenom2> [A-Z]\.)? (?P<nom>{_LETTERS})"
)
_YEAR_RE = re.compile(r"([1-9][0-9]{3})[.]")


@dataclass
class Author:
    """An author: surname and one or two initials."""

    nom: str
    prenom1: str
    prenom2: str | None = None


@dataclass
class AdwCitation:
    """Citation extracted from the ADW page of a taxon.

    `premier_auteur` is None when the page exists but carries no usable
    citation (e.g. a "classification" page alone).
    """

    premier_auteur: Author | None
    autres_auteurs: list[Author] = field(default_factory=list)
    annee: str | None = None


def _parse_author(match: re.Match[str]) -> Author:
    """Build an `Author` from a regex match."""
    return Author(
        nom=match.group("nom"),
        prenom1=match.group("prenom1"),
        prenom2=(match.group("prenom2") or "").strip() or None,
    )


def _parse_citation(html_page: str) -> AdwCitation:
    """Extract the citation of an ADW page."""
    block = _CITATION_BLOCK_RE.search(html_page)
    if block is None:
        return AdwCitation(premier_auteur=None)

    text = _TAG_RE.sub(" ", block.group("texte"))
    text = _html.unescape(" ".join(text.split()))

    first_match = _FIRST_AUTHOR_RE.search(text)
    if first_match is None:
        return AdwCitation(premier_auteur=None)

    rest = text[first_match.end() :]
    others = [_parse_author(m) for m in _OTHER_AUTHOR_RE.finditer(rest)]

    year_match = _YEAR_RE.search(text)

    return AdwCitation(
        premier_auteur=_parse_author(first_match),
        autres_auteurs=others,
        annee=year_match.group(1) if year_match else None,
    )


class AdwAdapter(OwnedClientMixin):
    """Raw ADW client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, follow_redirects=True)

    async def fetch(self, slug: str) -> AdwCitation | None:
        """Return the citation of taxon `slug`, or None if absent.

        `slug` has underscores for spaces. A citation whose
        `premier_auteur` is None means the page exists without a
        citation of its own.
        """
        html_page = await fetch_text(self._client, f"{BASE_URL}/accounts/{slug}/")
        if html_page is None:
            return None
        if _NOT_FOUND_RE.search(html_page):
            return None
        return _parse_citation(html_page)
