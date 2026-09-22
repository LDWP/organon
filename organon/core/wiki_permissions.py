"""Read the wiki page listing users allowed to trigger bot edits.

Page content is JSON: {"authorized_users": ["User1", "User2"]}.
Strictly fail-closed: any network error, missing page or invalid
content yields an empty list, never a stale cache. The page itself
must be write-protected by a frwiki administrator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin

logger = logging.getLogger(__name__)


class WikiPermissionChecker(OwnedClientMixin):
    """Check usernames against the cached permission page."""

    def __init__(
        self,
        *,
        api_url: str,
        page_title: str,
        ttl_seconds: float = 300.0,
        user_agent: str = USER_AGENT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure the page to read and the cache TTL."""
        self._api_url = api_url
        self._page_title = page_title
        self._ttl_seconds = ttl_seconds
        super().__init__(client, timeout=15.0, headers={"User-Agent": user_agent})
        self._cached_users: frozenset[str] = frozenset()
        self._cached_at: float | None = None
        self._refresh_lock = asyncio.Lock()

    async def is_authorized(self, username: str) -> bool:
        """Return True if `username` is on the permission page."""
        users = await self._authorized_users()
        return normalize_username(username) in users

    async def _authorized_users(self) -> frozenset[str]:
        if self._cache_valid():
            return self._cached_users
        async with self._refresh_lock:
            # Another call may have refreshed the cache while waiting.
            if self._cache_valid():
                return self._cached_users
            self._cached_users = await self._fetch_authorized_users()
            self._cached_at = time.monotonic()
        return self._cached_users

    def _cache_valid(self) -> bool:
        if self._cached_at is None:
            return False
        return (time.monotonic() - self._cached_at) < self._ttl_seconds

    async def _fetch_authorized_users(self) -> frozenset[str]:
        try:
            resp = await self._client.get(
                self._api_url,
                params={
                    "action": "query",
                    "prop": "revisions",
                    "titles": self._page_title,
                    "rvslots": "main",
                    "rvprop": "content",
                    "formatversion": "2",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Échec de lecture de la page de permission '%s' : %s (fail-closed, aucune "
                "autorisation accordée)",
                self._page_title,
                exc,
            )
            return frozenset()

        return _parse_authorized_users(payload, page_title=self._page_title)


def _parse_authorized_users(payload: dict, *, page_title: str) -> frozenset[str]:
    try:
        page = payload["query"]["pages"][0]
        if page.get("missing"):
            raise KeyError("page manquante")
        content = page["revisions"][0]["slots"]["main"]["content"]
        data = json.loads(content)
        users = data["authorized_users"]
        if not isinstance(users, list) or not all(isinstance(u, str) for u in users):
            raise TypeError("'authorized_users' doit être une liste de chaînes")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        logger.warning(
            "Contenu invalide sur la page de permission '%s' : %s (fail-closed, aucune "
            "autorisation accordée)",
            page_title,
            exc,
        )
        return frozenset()

    return frozenset(normalize_username(u) for u in users)


def normalize_username(username: str) -> str:
    """Normalize per MediaWiki: capitalized, underscores as spaces."""
    username = username.strip().replace("_", " ")
    return username[:1].upper() + username[1:] if username else username
