"""Network access to the EPPO Global Database (gd.eppo.int).

EPPO is the European and Mediterranean Plant Protection Organization.
`search()` uses the real JSON entry point the site's own autocomplete
uses. The taxon detail page has no JSON equivalent (the HTML page only),
hence a targeted regular expression, limited to the authority and the
French vernacular names, the only fields module.py consumes.
"""

from __future__ import annotations

import html
import re

from organon.core.http import OwnedClientMixin, fetch_text

BASE_URL = "https://gd.eppo.int"

_AUTHORITY_RE = re.compile(r"<strong>Authority:</strong>\s*([^<]+?)\s*</li>")
_FRENCH_ROW_RE = re.compile(
    r"<tr>\s*<td>([^<]+)</td>\s*<td class=\"text-center\">French[^<]*</td>\s*</tr>"
)


class OeppAdapter(OwnedClientMixin):
    """Raw EPPO Global Database client."""

    async def search(self, name: str) -> list[dict]:
        """Return the search results for a name."""
        resp = await self._client.get(
            f"{BASE_URL}/ajax/search", params={"k": name, "s": 1, "m": 1, "t": 0, "l": ""}
        )
        resp.raise_for_status()
        return resp.json() or []

    async def taxon_detail(self, eppo_code: str) -> dict:
        """Return the author and French vernacular names of a taxon.

        A dict `auteur` / `vernaculaire_fr`. Never None: a missing or
        empty page gives empty fields rather than failing the whole
        module (the id stays usable without the details).
        """
        text = await fetch_text(self._client, f"{BASE_URL}/taxon/{eppo_code}")
        if text is None:
            return {"auteur": None, "vernaculaire_fr": []}

        author = None
        m = _AUTHORITY_RE.search(text)
        if m:
            author = html.unescape(m.group(1)).strip() or None

        vernacular = [html.unescape(m.group(1)).strip() for m in _FRENCH_ROW_RE.finditer(text)]

        return {"auteur": author, "vernaculaire_fr": vernacular}
