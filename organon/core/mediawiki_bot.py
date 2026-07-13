"""Client du compte bot dédié : authentification par Bot Password (`Special:BotPasswords`) puis
édition de pages via `action=edit`.

Séquence conforme à [API:Login](https://www.mediawiki.org/wiki/API:Login) et
[API:Edit](https://www.mediawiki.org/wiki/API:Edit) : `action=login` reste la méthode valide
pour les comptes Bot Password (contrairement aux comptes normaux, pour qui elle est dépréciée au
profit de `clientlogin`). Les cookies de session sont conservés automatiquement par
`httpx.AsyncClient` d'une requête à l'autre (comme `requests.Session`), ce qui est indispensable
au bon fonctionnement du login.

Ce client n'est PAS branché en production tant que le statut du bot n'a pas été tranché par la
communauté — voir `AuthSettings.bot_edit_enabled` et `organon.api.routes.taxobox_refresh`.
"""

from __future__ import annotations

import httpx


class BotEditError(RuntimeError):
    """Levée quand l'API MediaWiki refuse la connexion ou l'édition du compte bot."""


class MediaWikiBotClient:
    def __init__(
        self,
        *,
        api_url: str,
        username: str,
        password: str,
        user_agent: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_url = api_url
        self._username = username
        self._password = password
        self._client = client or httpx.AsyncClient(timeout=30.0, headers={"User-Agent": user_agent})
        self._owns_client = client is None
        self._logged_in = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_token(self, token_type: str) -> str:
        resp = await self._client.get(
            self._api_url,
            params={"action": "query", "meta": "tokens", "type": token_type, "format": "json"},
        )
        resp.raise_for_status()
        payload = resp.json()
        try:
            return payload["query"]["tokens"][f"{token_type}token"]
        except KeyError as exc:
            raise BotEditError(
                f"Réponse inattendue de l'API lors de la récupération du jeton "
                f"'{token_type}' : {payload}"
            ) from exc

    async def _login(self) -> None:
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

    async def edit_page(self, *, title: str, text: str, summary: str) -> dict:
        await self._login()
        csrf_token = await self._get_token("csrf")
        resp = await self._client.post(
            self._api_url,
            data={
                "action": "edit",
                "title": title,
                "text": text,
                "summary": summary,
                "token": csrf_token,
                "maxlag": "5",
                "format": "json",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise BotEditError(f"Erreur API MediaWiki lors de l'édition : {payload['error']}")
        edit_result = payload.get("edit", {})
        if edit_result.get("result") != "Success":
            raise BotEditError(f"Édition refusée par MediaWiki : {edit_result}")
        return edit_result
