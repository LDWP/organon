"""Network access to POWO (Plants of the World Online).

Called directly on `https://powo.science.kew.org/api/2`, without
`pykew`, which does not compile everywhere. `requests` stays necessary:
POWO sits behind a Cloudflare challenge that refuses `httpx` (403)
whatever the User-Agent but accepts `requests` with the Organon one.
Synchronous calls run in a thread.

The API answers 404 with `{"error": "Not Found"}` for an unknown id:
`lookup()` returns None. Status 249 means "too many requests": retried
at most `MAX_BUSY_ATTEMPTS` times. Kew recommends staying under about 5
requests/s.

Sub-taxa: `lookup()` already returns `childNameUsages` (the accepted
direct children, one level, never recursive), with no extra parameter or
request and no API-side truncation.
"""

from __future__ import annotations

import asyncio
import logging
import time

import requests

from organon.core.http import USER_AGENT, MinIntervalThrottle

logger = logging.getLogger(__name__)

BASE_URL = "https://powo.science.kew.org/api/2"
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
_TIMEOUT = 30

# Bound on the results kept from a search (a page of 500 is asked):
# plenty to filter on an exact name match.
MAX_RESULTS = 50

_PAGE_SIZE = 500
_MIN_INTERVAL = 0.2  # ~5 requests/s
_BUSY_STATUS = 249
MAX_BUSY_ATTEMPTS = 3
_BUSY_DELAY = 5

_throttle = MinIntervalThrottle(_MIN_INTERVAL).wait


def _get_json(path: str, params: dict) -> object:
    """GET a POWO path, retrying while the service is busy (249)."""
    for attempt in range(MAX_BUSY_ATTEMPTS):
        resp = requests.get(
            f"{BASE_URL}/{path}", params=params, headers=_HEADERS, timeout=_TIMEOUT
        )
        if resp.status_code != _BUSY_STATUS:
            return resp.json()
        if attempt < MAX_BUSY_ATTEMPTS - 1:
            time.sleep(_BUSY_DELAY)
    raise requests.exceptions.RetryError(f"POWO occupé (249) après {MAX_BUSY_ATTEMPTS} essais")


class PowoAdapter:
    """Raw POWO API client."""

    async def search(self, name: str) -> list[dict]:
        """Return up to `MAX_RESULTS` search results; [] on failure."""
        await _throttle()
        params = {"q": name, "perPage": _PAGE_SIZE, "cursor": "*"}
        try:
            data = await asyncio.to_thread(_get_json, "search", params)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("POWO : recherche de « %s » impossible (%s)", name, exc)
            return []
        if not isinstance(data, dict):
            return []
        return (data.get("results") or [])[:MAX_RESULTS]

    async def lookup(self, taxon_id: str, include: list[str] | None = None) -> dict | None:
        """Return the full record of a taxon id, or None."""
        await _throttle()
        params = {"fields": ",".join(include)} if include else {}
        try:
            result = await asyncio.to_thread(_get_json, f"taxon/{taxon_id}", params)
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("POWO : lecture de %s impossible (%s)", taxon_id, exc)
            return None
        if not isinstance(result, dict) or "error" in result:
            return None
        return result
