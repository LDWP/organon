"""Adaptateur Wikispecies : existence de page via l'API MediaWiki standard."""

from __future__ import annotations

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.modules.common import mediawiki_page_exists

API_URL = "https://species.wikimedia.org/w/api.php"


class SpeciesAdapter(OwnedClientMixin):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def page_exists(self, title: str) -> bool:
        return await mediawiki_page_exists(self._client, API_URL, title)
