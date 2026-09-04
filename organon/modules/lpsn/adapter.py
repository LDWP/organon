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
(recherche par critères nommés -> liste d'identifiants, paginée par `next`), `fetch` (fiches
complètes pour une liste d'identifiants séparés par `;`) et `flexible_search` (recherche par
requête JSON arbitraire sur n'importe quel champ de fiche, même pagination par `next`). Pas de
route dédiée à la hiérarchie (pas d'équivalent à `AphiaChildrenByAphiaID` de WoRMS), mais chaque
fiche porte son `lpsn_parent_id` (voir `module.py`), et celui-ci est un champ de fiche comme un
autre : `flexible_search({"lpsn_parent_id": id})` retrouve donc les enfants directs d'un taxon
sans route dédiée. Toujours pas de route pour les synonymes d'un identifiant donné (seul le sens
inverse, `lpsn_correct_name_id` porté par chaque synonyme, est exploité) : `struct.synonymes`
reste hors périmètre de ce module.

Noms de champs JSON (voir `module.py`) tirés de la documentation publique
(https://lpsn.dsmz.de/text/lpsn-api), vérifiés depuis contre l'API réelle. Un écart notable :
`lpsn_address` ne contient pas l'URL conviviale du site (ex. "https://lpsn.dsmz.de/genus/
dichelobacter") contrairement à ce que dit la doc, mais le lien DOI permanent de la fiche (ex.
"https://doi.org/10.83108/rn.515525") — `module.py` reconstruit donc l'identifiant du modèle
Wikipédia {{LPSN}} depuis `monomial`/`species_epithet`/`subspecies_epithet` plutôt que depuis ce
champ (voir `_slug_from_record`)."""

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
    """Échec d'authentification LPSN (identifiants absents ou refusés par Keycloak)."""


class LpsnAdapter(OwnedClientMixin):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(client)
        settings = get_auth_settings()
        self._username = username if username is not None else settings.lpsn_username
        self._password = password if password is not None else settings.lpsn_password
        self._access_token: str | None = None
        self._refresh_token: str | None = None

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

    async def flexible_search(self, search: dict[str, object]) -> list[int]:
        """Recherche par requête JSON arbitraire sur les champs d'une fiche (voir
        https://lpsn.dsmz.de/text/lpsn-api) -> liste d'identifiants LPSN, agrégée sur toutes les
        pages (`next`), même forme de réponse que `advanced_search`."""
        url: str | None = f"{BASE_URL}/flexible_search"
        query: dict[str, str] | None = {"search": json.dumps(search)}
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

    async def resolve_doi_citation(self, doi: str) -> str | None:
        """Résolution DOI -> citation wikitexte partagée avec WoRMS (voir
        `organon.modules.bibliography`) : n'interroge ni `api.lpsn.dsmz.de` ni Keycloak, donc pas
        besoin du token porteur — `self._client` nu convient (`_auth_header` n'est ajouté
        qu'explicitement par `_get`, jamais par défaut sur le client)."""
        return await resolve_doi_citation(self._client, doi)
