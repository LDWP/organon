"""Network access to Tropicos (tropicos.org/api): raw HTTP and JSON.

The token (`AuthSettings.tropicos_token`) is the public one the site's
own search widget uses client-side, not a personal token. As it is not
officially documented, it may be revoked or changed without notice, in
which case the module fails cleanly (non-200 HTTP status), not
silently.
"""

from __future__ import annotations

import httpx

from organon.core.auth_settings import get_auth_settings
from organon.core.http import MinIntervalThrottle, OwnedClientMixin

BASE_URL = "https://www.tropicos.org/api"
_throttle = MinIntervalThrottle(0.2).wait


class TropicosAdapter(OwnedClientMixin):
    """Raw Tropicos API client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        headers = {
            "Authorization": f"Bearer {get_auth_settings().tropicos_token}",
            "Referer": "https://www.tropicos.org/name/Search",
        }
        super().__init__(client, headers=headers, throttle=_throttle)

    async def search(self, name: str) -> list[dict]:
        """Return the name records matching `name`."""
        resp = await self._client.get(
            f"{BASE_URL}/Search/NameLookup",
            params={"value": name, "returnCount": 10, "lookupType": 1},
        )
        resp.raise_for_status()
        return resp.json() or []
