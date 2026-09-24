"""Network access to LPSN (api.lpsn.dsmz.de): raw HTTP and JSON only.

LPSN needs an individually registered account (see
`AuthSettings.lpsn_username`), unlike the other REST sources.
Authentication goes through Keycloak (OAuth2 password grant, public
client `api.lpsn.public`), done by plain HTTP to avoid a dependency for
one module. The access token lasts about 15 minutes; it is renewed with
the refresh token on a 401, or re-authenticated from scratch if that
fails too.

The API has three routes: `advanced_search` (named criteria to ids,
paginated by `next`), `fetch` (full records for `;`-separated ids) and
`flexible_search` (JSON query on any record field). There is no
hierarchy route, but each record carries `lpsn_parent_id`, so
`flexible_search({"lpsn_parent_id": id})` finds the direct children.
There is no route for the synonyms of an id, so `struct.synonyms` is out
of scope.

`lpsn_address` holds the permanent DOI link, not the friendly site URL;
`module.py` rebuilds the {{LPSN}} id from the name parts instead (see
`_slug_from_record`).
"""

from __future__ import annotations

import json

import httpx

from organon.core.auth_settings import get_auth_settings
from organon.core.http import OwnedClientMixin
from organon.modules.bibliography import resolve_doi_citation

TOKEN_URL = "https://sso.dsmz.de/auth/realms/dsmz/protocol/openid-connect/token"
KEYCLOAK_CLIENT_ID = "api.lpsn.public"
BASE_URL = "https://api.lpsn.dsmz.de"


class LpsnAuthError(RuntimeError):
    """LPSN authentication failed (missing or refused credentials)."""


class LpsnAdapter(OwnedClientMixin):
    """Authenticated client of the LPSN API."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Use the given credentials, else the configured ones."""
        super().__init__(client)
        settings = get_auth_settings()
        self._username = username if username is not None else settings.lpsn_username
        self._password = password if password is not None else settings.lpsn_password
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    async def _authenticate(self) -> None:
        """Get an access token with the password grant."""
        if not self._username or not self._password:
            raise LpsnAuthError(
                "Identifiants LPSN absents (ORGANON_LPSN_USERNAME/ORGANON_LPSN_PASSWORD) : "
                "inscription requise sur https://register.lpsn.dsmz.de/."
            )
        resp = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": KEYCLOAK_CLIENT_ID,
                "username": self._username,
                "password": self._password,
            },
        )
        if resp.status_code != 200:
            raise LpsnAuthError(f"Authentification LPSN refusée (HTTP {resp.status_code}).")
        token = resp.json()
        self._access_token = token["access_token"]
        self._refresh_token = token.get("refresh_token")

    async def _refresh(self) -> bool:
        """Renew the access token; return False if impossible."""
        if not self._refresh_token:
            return False
        resp = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": KEYCLOAK_CLIENT_ID,
                "refresh_token": self._refresh_token,
            },
        )
        if resp.status_code != 200:
            return False
        token = resp.json()
        self._access_token = token["access_token"]
        self._refresh_token = token.get("refresh_token")
        return True

    def _auth_header(self) -> dict[str, str]:
        """Return the bearer authorization header."""
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _get(self, url: str, params: dict[str, str] | None = None) -> dict:
        """GET with the token, renewing it once on a 401."""
        if self._access_token is None:
            await self._authenticate()
        resp = await self._client.get(url, params=params, headers=self._auth_header())
        if resp.status_code == 401:
            if not await self._refresh():
                await self._authenticate()
            resp = await self._client.get(url, params=params, headers=self._auth_header())
        resp.raise_for_status()
        return resp.json()

    async def advanced_search(self, **params: str) -> list[int]:
        """Search by criteria (e.g. `taxon_name=...`); return LPSN ids.

        Aggregates all pages (`next`). Underscores in `params` become
        hyphens for the API (`taxon_name` to `taxon-name`).
        """
        query: dict[str, str] | None = {k.replace("_", "-"): v for k, v in params.items()}
        url: str | None = f"{BASE_URL}/advanced_search"
        ids: list[int] = []
        while url:
            data = await self._get(url, params=query)
            ids.extend(data.get("results") or [])
            url = data.get("next")
            query = None  # `next` is already a full URL with its own query string

        return ids

    async def flexible_search(self, search: dict[str, object]) -> list[int]:
        """Search by a JSON query on record fields; return LPSN ids.

        Aggregates all pages (`next`), like `advanced_search`.
        """
        url: str | None = f"{BASE_URL}/flexible_search"
        query: dict[str, str] | None = {"search": json.dumps(search)}
        ids: list[int] = []
        while url:
            data = await self._get(url, params=query)
            ids.extend(data.get("results") or [])
            url = data.get("next")
            query = None  # `next` is already a full URL with its own query string

        return ids

    async def fetch(self, ids: list[int]) -> list[dict]:
        """Return the full records of LPSN ids (`fetch/id1;id2;...`).

        `results` may be a list of records or a dict {id: record}; both
        forms are handled.
        """
        if not ids:
            return []
        url = f"{BASE_URL}/fetch/{';'.join(str(i) for i in ids)}"
        data = await self._get(url)
        results = data.get("results")
        if isinstance(results, dict):
            return list(results.values())
        return results or []

    async def fetch_one(self, taxon_id: int) -> dict | None:
        """Return the record of one id, or None."""
        records = await self.fetch([taxon_id])
        return records[0] if records else None

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Resolve a DOI into a wikitext citation.

        Shared with WoRMS (`organon.modules.bibliography`). It calls
        neither LPSN nor Keycloak, so the bare client needs no token.
        """
        return await resolve_doi_citation(self._client, doi)
