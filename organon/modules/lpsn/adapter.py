"""Couche d'accès réseau pour LPSN (api.lpsn.dsmz.de) : appels HTTP et décodage JSON bruts
uniquement.

Contrairement aux autres sources REST du projet, LPSN exige un compte utilisateur enregistré
(inscription gratuite sur https://register.lpsn.dsmz.de/, voir
`organon.core.auth_settings.AuthSettings.lpsn_username`/`lpsn_password`) : pas de jeton public
partageable comme celui utilisé par `organon.modules.tropicos`. L'authentification passe par
Keycloak (grant OAuth2 "password", client public `api.lpsn.public`, realm `dsmz`), reproduite ici
en HTTP direct plutôt que via la dépendance `python-keycloak` du client de référence
(https://github.com/LeibnizDSMZ/lpsn-api/blob/master/lpsn/client.py) pour ne pas ajouter de
dépendance au projet pour un seul module (le reste du projet utilise `httpx` partout). Le jeton
d'accès est valide ~15 minutes d'après ce client de référence ; renouvelé via le jeton de
rafraîchissement sur un 401, ou ré-authentifié depuis zéro si le rafraîchissement échoue aussi.

L'API LPSN n'expose que trois routes (voir https://api.lpsn.dsmz.de/) : `advanced_search`
(recherche -> liste d'identifiants, paginée par `next`), `fetch` (fiches complètes pour une liste
d'identifiants séparés par `;`) et `flexible_search` (non utilisée ici). Pas de route pour lister
les synonymes ou sous-taxons d'un identifiant donné : `module.py` ne peut donc pas remplir
`struct.synonymes`/`struct.sous_taxons`, contrairement à WoRMS/POWO (limitation de l'API, pas un
oubli).

Noms de champs JSON (voir `module.py`) tirés de la documentation publique
(https://lpsn.dsmz.de/text/lpsn-api) faute de compte de test disponible pour vérifier contre une
réponse réelle au moment de l'écriture (voir `docs/md/db-inventory.md` : LPSN classé
"contact_requis") — à valider dès qu'un compte est enregistré."""

from __future__ import annotations

import httpx

from organon.core.auth_settings import get_auth_settings

TOKEN_URL = "https://sso.dsmz.de/auth/realms/dsmz/protocol/openid-connect/token"
KEYCLOAK_CLIENT_ID = "api.lpsn.public"
BASE_URL = "https://api.lpsn.dsmz.de"


class LpsnAuthError(RuntimeError):
    """Échec d'authentification LPSN (identifiants absents ou refusés par Keycloak)."""


class LpsnAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        settings = get_auth_settings()
        self._username = username if username is not None else settings.lpsn_username
        self._password = password if password is not None else settings.lpsn_password
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _authenticate(self) -> None:
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
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _get(self, url: str, params: dict[str, str] | None = None) -> dict:
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
        """Recherche par critères (ex. `taxon_name=...`) -> liste d'identifiants LPSN, agrégée
        sur toutes les pages (`next`). `params` utilise des underscores (convention Python),
        convertis en tirets pour l'API (ex. `taxon_name` -> `taxon-name`), comme le fait le
        client de référence."""
        query: dict[str, str] | None = {k.replace("_", "-"): v for k, v in params.items()}
        url: str | None = f"{BASE_URL}/advanced_search"
        ids: list[int] = []
        while url:
            data = await self._get(url, params=query)
            ids.extend(data.get("results") or [])
            url = data.get("next")
            query = None  # `next` est déjà une URL complète avec sa propre query string

        return ids

    async def fetch(self, ids: list[int]) -> list[dict]:
        """Fiches complètes pour une liste d'identifiants LPSN (`fetch/id1;id2;...`). D'après le
        client de référence, `results` peut être soit une liste de fiches, soit un dict
        {id: fiche} (`isinstance` gérée des deux côtés dans ce client) : les deux formes sont
        donc gérées ici aussi plutôt que de supposer laquelle l'API renvoie réellement."""
        if not ids:
            return []
        url = f"{BASE_URL}/fetch/{';'.join(str(i) for i in ids)}"
        data = await self._get(url)
        results = data.get("results")
        if isinstance(results, dict):
            return list(results.values())
        return results or []

    async def fetch_one(self, taxon_id: int) -> dict | None:
        records = await self.fetch([taxon_id])
        return records[0] if records else None
