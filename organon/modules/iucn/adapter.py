"""Network access to the IUCN Red List API v4 (api.iucnredlist.org).

Raw HTTP and JSON only; see module.py.

A free individual token is required (see `AuthSettings.iucn_api_token`):
IUCN offers no shareable public token, so each deployment must register
its own.
"""

from __future__ import annotations

import httpx

from organon.core.auth_settings import get_auth_settings
from organon.core.http import OwnedClientMixin, fetch_json

BASE_URL = "https://api.iucnredlist.org/api/v4"


class IucnAdapter(OwnedClientMixin):
    """Raw IUCN Red List API client."""

    def __init__(self, client: httpx.AsyncClient | None = None, token: str | None = None) -> None:
        """Use the given token, else the configured one."""
        self._token = token if token is not None else get_auth_settings().iucn_api_token
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        super().__init__(client, headers=headers)

    async def scientific_name(
        self, genus_name: str, species_name: str, infra_name: str | None = None
    ) -> dict | None:
        """Return the `/taxa/scientific_name` result, or None.

        The taxon identity and the full history of its assessments (see
        `module.py` for the one retained). That answer already carries
        `red_list_category_code` and `criteria` per assessment, the only
        fields used, so there is no separate `/assessment/{id}` call.
        """
        if not self._token:
            # No token: the module is simply skipped, with no network
            # call doomed to a 401.
            return None
        params: dict[str, str] = {"genus_name": genus_name, "species_name": species_name}
        if infra_name:
            params["infra_name"] = infra_name
        return await fetch_json(self._client, f"{BASE_URL}/taxa/scientific_name", params=params)
