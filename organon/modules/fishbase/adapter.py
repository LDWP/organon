"""Network access to the FishBase site (https://www.fishbase.se).

The ChecklistBank export (see module.py) carries WoRMS identifiers,
not the numeric FishBase codes that `{{FishBase espèce}}` and
`{{FishBase famille}}` require. The codes are read from the public
pages, addressed by name. `fishbase.org` answers 403 to non-browser
clients; `fishbase.se` serves the same pages.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from organon.core.http import USER_AGENT, MinIntervalThrottle, OwnedClientMixin, fetch_text

BASE_URL = "https://www.fishbase.se/summary"

_MIN_INTERVAL = 1.0
_SPECIES_CODE = re.compile(r"SpeciesSummary\.php\?id=(\d+)")
_FAMILY_CODE = re.compile(r"[?&]famcode=(\d+)")
_SPECIES_NAME = re.compile(r"[A-Z][a-z]+ [a-z-]+")

_throttle = MinIntervalThrottle(_MIN_INTERVAL).wait


class FishbaseSiteAdapter(OwnedClientMixin):
    """Raw FishBase page client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def species_code(self, name: str) -> str | None:
        """Return the SpecCode of a binomial, or None if unknown."""
        if not _SPECIES_NAME.fullmatch(name):
            return None
        return await self._code(f"{BASE_URL}/{name.replace(' ', '-')}.html", _SPECIES_CODE)

    async def family_code(self, name: str) -> str | None:
        """Return the FamCode of a family, or None if unknown."""
        return await self._code(
            f"{BASE_URL}/FamilySummary.php?family={quote(name)}", _FAMILY_CODE
        )

    async def _code(self, url: str, pattern: re.Pattern[str]) -> str | None:
        """Return the first code matched by `pattern`.

        An unknown name still answers 200 with a generic page: no match
        means absent.
        """
        await _throttle()
        html = await fetch_text(self._client, url)
        match = pattern.search(html) if html else None
        return match.group(1) if match else None
