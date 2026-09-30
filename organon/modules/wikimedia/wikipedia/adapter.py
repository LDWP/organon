"""French Wikipedia adapter.

Read the wikitext of a taxon's article (family, order or class, see
module.py) and extract the portals it already declares through
`{{Portail|...}}`, rather than guess from the rendered hidden
categories, which include parent portals by cascade.

`redirects=1`: scientific names of class or order rank often redirect to
the vernacular name (Aves to Oiseau); without it `prop=revisions` would
return the redirect page itself.

French edition only for now.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.modules.common import mediawiki_page_exists

API_URL = "https://fr.wikipedia.org/w/api.php"

_PORTAL_RE = re.compile(r"\{\{\s*[Pp]ortail\s*\|([^}]+)\}\}")


def _extract_portals(wikitext: str) -> list[str]:
    """Return the portals declared by `{{Portail|...}}`."""
    match = _PORTAL_RE.search(wikitext)
    if not match:
        return []
    return [p.strip() for p in match.group(1).split("|") if p.strip()]


class WikitextPage(NamedTuple):
    """Wikitext of an article, with its revision."""

    title: str
    content: str
    revid: int
    timestamp: str


class WikipediaAdapter(OwnedClientMixin):
    """French Wikipedia client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def wikitext(self, title: str) -> WikitextPage | None:
        """Return the wikitext of article `title`, or None if missing.

        A redirect is followed and `title` is the resolved article.
        """
        params = {
            "action": "query",
            "titles": title,
            "redirects": "1",
            "prop": "revisions",
            "rvprop": "content|ids|timestamp",
            "rvslots": "main",
            "formatversion": "2",
            "format": "json",
        }
        resp = await self._client.get(API_URL, params=params)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages") or []
        if not pages or pages[0].get("missing"):
            return None
        revisions = pages[0].get("revisions")
        if not revisions:
            return None
        revision = revisions[0]
        return WikitextPage(
            pages[0]["title"],
            revision["slots"]["main"]["content"],
            revision["revid"],
            revision["timestamp"],
        )

    async def category_exists(self, name: str) -> bool:
        """Return True if the category exists."""
        return await mediawiki_page_exists(self._client, API_URL, f"Catégorie:{name}")

    async def portails(self, title: str) -> list[str] | None:
        """Return the portals declared by article `title`.

        A redirect is followed. None if the page is missing or declares
        no `{{Portail}}`.
        """
        page = await self.wikitext(title)
        return (_extract_portals(page.content) or None) if page else None
