"""Client for the dedicated bot account.

Bot Password login (`action=login`, still valid for bot passwords)
then page edits through `action=edit`. Session cookies persist on
the `httpx.AsyncClient`, which login requires. Not wired in
production; see `AuthSettings.bot_edit_enabled`.
"""

from __future__ import annotations

import asyncio

import httpx

from organon.core.http import OwnedClientMixin


class BotEditError(RuntimeError):
    """MediaWiki refused the bot login or edit."""


class BotEditConflictError(BotEditError):
    """The page changed since the base revision."""


class BotMaxLagError(BotEditError):
    """Replication lag; retry after `retry_after` seconds."""

    def __init__(self, message: str, retry_after: float = 5.0) -> None:
        """Store the suggested retry delay."""
        super().__init__(message)
        self.retry_after = retry_after


class MediaWikiBotClient(OwnedClientMixin):
    """Logged-in MediaWiki client for the bot account."""

    def __init__(
        self,
        *,
        api_url: str,
        username: str,
        password: str,
        user_agent: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Store credentials; use `client` if given."""
        self._api_url = api_url
        self._username = username
        self._password = password
        super().__init__(client, timeout=30.0, headers={"User-Agent": user_agent})
        self._logged_in = False
        self._login_lock = asyncio.Lock()

    async def _get_token(self, token_type: str) -> str:
        resp = await self._client.get(
            self._api_url,
            params={"action": "query", "meta": "tokens", "type": token_type, "format": "json"},
        )
        resp.raise_for_status()
        payload = resp.json()
        try:
            token: str = payload["query"]["tokens"][f"{token_type}token"]
            return token
        except KeyError as exc:
            raise BotEditError(
                f"Réponse inattendue de l'API lors de la récupération du jeton "
                f"'{token_type}' : {payload}"
            ) from exc

    async def _login(self) -> None:
        if self._logged_in:
            return
        async with self._login_lock:
            if self._logged_in:
                return
            login_token = await self._get_token("login")
            resp = await self._client.post(
                self._api_url,
                data={
                    "action": "login",
                    "lgname": self._username,
                    "lgpassword": self._password,
                    "lgtoken": login_token,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            result = resp.json().get("login", {})
            if result.get("result") != "Success":
                raise BotEditError(f"Échec de connexion du compte bot : {result}")
            self._logged_in = True

    async def edit_page(
        self,
        *,
        title: str,
        text: str,
        summary: str,
        baserevid: int | None = None,
        basetimestamp: str | None = None,
        nocreate: bool = False,
        bot: bool = False,
    ) -> dict:
        """Edit a page, logging in first if needed.

        Raise `BotEditConflictError` on edit conflicts and
        `BotMaxLagError` on replication lag. Return the API `edit`
        result.
        """
        await self._login()
        csrf_token = await self._get_token("csrf")
        data = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "token": csrf_token,
            "maxlag": "5",
            "assert": "user",
            "format": "json",
        }
        if baserevid is not None:
            data["baserevid"] = str(baserevid)
        if basetimestamp is not None:
            data["basetimestamp"] = basetimestamp
        if nocreate:
            data["nocreate"] = "1"
        if bot:
            data["bot"] = "1"
        resp = await self._client.post(self._api_url, data=data)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            erreur = payload["error"]
            message = f"Erreur API MediaWiki lors de l'édition : {erreur}"
            if erreur.get("code") == "editconflict":
                raise BotEditConflictError(message)
            if erreur.get("code") == "maxlag":
                raise BotMaxLagError(message, float(resp.headers.get("Retry-After", 5)))
            raise BotEditError(message)
        edit_result = payload.get("edit", {})
        if edit_result.get("result") != "Success":
            raise BotEditError(f"Édition refusée par MediaWiki : {edit_result}")
        result: dict = edit_result
        return result
