"""French Wiktionary adapter: page existence, via the MediaWiki API."""

from __future__ import annotations

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.modules.common import mediawiki_page_exists

API_URL = "https://fr.wiktionary.org/w/api.php"


class WiktionnaireAdapter(OwnedClientMixin):
    """French Wiktionary client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def page_exists(self, title: str) -> bool:
        """Return True if the page exists."""
        return await mediawiki_page_exists(self._client, API_URL, title)
