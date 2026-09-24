"""Network access to TAXREF/INPN.

Name search (`GET .../api/taxa/search?nomComplet=...`) is JSON, but the
server-side match is fuzzy (substring, relevance): a common name may
return dozens of unrelated homonyms before the exact entry (a search for
"Vulpes" first returns `Albula vulpes`, a fish). `nb_rows` is
deliberately wide (500) to make the exact entry likely present; the
strict selection by `cdNom` and `lbNom` is left to `module.py`.

The detail page (`GET .../taxa/{cdNom}`) is HTML (JSP), not JSON. No
endpoint like ITIS's `getFullHierarchyFromTSN` exists: the page
breadcrumb gives the ancestors (name, id) in one call but not their
rank, resolved ancestor by ancestor through `search()` in module.py.

The taxref.mnhn.fr WAF answered 403 to the Toolforge IP with httpx's
default `User-Agent`; requests carry the honest Organon one.
"""

from __future__ import annotations

import html
import re

import httpx

from organon.core.http import MinIntervalThrottle, OwnedClientMixin

API_BASE = "https://taxref.mnhn.fr/taxref-web/api"
WEB_BASE = "https://taxref.mnhn.fr/taxref-web"

_throttle = MinIntervalThrottle(0.2).wait

_HEADERS = {
    "Accept": "application/json, text/html, */*",
}

_BREADCRUMB_RE = re.compile(
    r'<a href="/taxref-web/taxa/(?P<id>\d+)">(?P<nom>[^<]+)</a>\s*&rsaquo;'
)
_VERNACULAR_BLOCK_RE = re.compile(
    r"<legend>NOMS VERNACULAIRES</legend>(?P<block>.*?)</fieldset>", re.DOTALL
)
# Several names may share one <span>, comma-separated (e.g. "Renard
# roux, Renard, Goupil" for Vulpes vulpes): split by the caller.
_VERNACULAR_ENTRY_RE = re.compile(
    r"<span>(?P<noms>[^<]+)</span>\s*\(<a[^>]*>(?P<langue>[^<]+)</a>", re.DOTALL
)


class InpnAdapter(OwnedClientMixin):
    """Raw TAXREF client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, headers=_HEADERS, throttle=_throttle)

    async def search(self, full_name: str, nb_rows: int = 500) -> list[dict]:
        """Return the TAXREF search results for a full name."""
        resp = await self._client.get(
            f"{API_BASE}/taxa/search", params={"nomComplet": full_name, "nbRows": nb_rows}
        )
        resp.raise_for_status()
        return resp.json()

    async def detail_html(self, cd_nom: int) -> str:
        """Return the HTML detail page of a `cdNom`."""
        resp = await self._client.get(f"{WEB_BASE}/taxa/{cd_nom}")
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def parse_breadcrumb(html_page: str) -> list[tuple[int, str]]:
        """Return the full lineage, root first, up to the parent.

        The taxon itself is not in its own breadcrumb.
        """
        return [
            (int(m.group("id")), html.unescape(m.group("nom")).strip())
            for m in _BREADCRUMB_RE.finditer(html_page)
        ]

    @staticmethod
    def parse_vernacular_french(html_page: str) -> list[str]:
        """Return the French vernacular names of a detail page."""
        block_match = _VERNACULAR_BLOCK_RE.search(html_page)
        if block_match is None:
            return []
        out: list[str] = []
        for m in _VERNACULAR_ENTRY_RE.finditer(block_match.group("block")):
            if m.group("langue").strip() != "Français":
                continue
            out.extend(
                html.unescape(name).strip() for name in m.group("noms").split(",") if name.strip()
            )
        return out
