"""HTTP helpers shared by the module adapters."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Self

import httpx

USER_AGENT = "Organon/0.1 (https://fr.wikipedia.org/wiki/Projet:Biologie/Organon)"


_Throttle = Callable[[], Awaitable[None]]
_RequestHook = Callable[[httpx.Request], Awaitable[None]]


def _wait_hook(throttle: _Throttle) -> _RequestHook:
    async def hook(_request: httpx.Request) -> None:
        await throttle()

    return hook


class OwnedClientMixin:
    """Hold an injected or self-created `httpx.AsyncClient`.

    A self-created client sends the Organon `User-Agent` unless
    `headers` overrides it. `throttle`, if given, is awaited before each
    request of a self-created client.
    `aclose()` only closes a client the adapter created itself.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
        throttle: _Throttle | None = None,
    ) -> None:
        """Use `client` if given, else create one."""
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            follow_redirects=follow_redirects,
            event_hooks={"request": [_wait_hook(throttle)]} if throttle else None,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        """Close the client if this adapter owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        """Enter the async context."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Close the client on exit."""
        await self.aclose()


class MinIntervalThrottle:
    """Space calls by at least `min_interval` seconds, process-wide.

    Instantiate once per module, not per adapter (adapters are
    recreated on each request).
    """

    def __init__(self, min_interval: float) -> None:
        """Set the minimum interval between calls."""
        self._min_interval = min_interval
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Sleep until the next call is allowed."""
        async with self._lock:
            delay = self._last_call + self._min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_call = time.monotonic()


async def _get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None,
    headers: dict[str, str] | None,
    empty_statuses: tuple[int, ...],
) -> httpx.Response | None:
    """GET returning None for `empty_statuses` (e.g. 404, absent).

    Any other status >= 400 raises, so callers can tell "absent" from
    a transient failure.
    """
    resp = await client.get(url, params=params, headers=headers)
    if resp.status_code in empty_statuses:
        return None
    resp.raise_for_status()
    return resp


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    empty_statuses: tuple[int, ...] = (404,),
    empty_value: Any = None,
) -> Any:
    """GET and decode JSON.

    Return `empty_value` for `empty_statuses` and for an empty body
    (some APIs answer 204 for an absent resource).
    """
    resp = await _get(client, url, params=params, headers=headers, empty_statuses=empty_statuses)
    if resp is None or not resp.content:
        return empty_value
    return resp.json()


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    empty_statuses: tuple[int, ...] = (404,),
) -> str | None:
    """GET the raw body, returning None for `empty_statuses`.

    Same contract as `fetch_json`.
    """
    resp = await _get(client, url, params=params, headers=headers, empty_statuses=empty_statuses)
    return None if resp is None else resp.text
