"""Lecture et validation de la page wiki listant les utilisateurs autorisés à déclencher une
édition par le compte bot dédié.

Format de page attendu (JSON, ex. `Wikipédia:Projet:Biologie/Taxobot/user.json` — chemin réel de
page wiki, pas un identifiant du logiciel : garder « Taxobot » ici tant que la page/décision
communautaire correspondante n'a pas de nom définitif, voir `AuthSettings.permission_page_title`) :

    {"authorized_users": ["Utilisateur1", "Utilisateur2"]}

Fail-closed strict, sans exception : toute erreur réseau, page manquante, ou contenu qui n'est
pas un JSON valide de cette forme précise entraîne une liste d'autorisation VIDE, jamais une
liste héritée d'un cache précédent ni une interprétation permissive (la page de permission est
elle-même une cible d'escalade de privilège, et une page wiki reste éditable par erreur). Cette
page elle-même doit être protégée en écriture par un administrateur frwiki avant mise en service
réelle (prérequis humain, non traité par ce module).
"""

from __future__ import annotations

import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)


class WikiPermissionChecker:
    def __init__(
        self,
        *,
        api_url: str,
        page_title: str,
        ttl_seconds: float = 300.0,
        user_agent: str = "Organon/0.1 (permission-check)",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_url = api_url
        self._page_title = page_title
        self._ttl_seconds = ttl_seconds
        self._client = client or httpx.AsyncClient(timeout=15.0, headers={"User-Agent": user_agent})
        self._owns_client = client is None
        self._cached_users: frozenset[str] = frozenset()
        self._cached_at: float | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def is_authorized(self, username: str) -> bool:
        users = await self._authorized_users()
        return _normalize_username(username) in users

    async def _authorized_users(self) -> frozenset[str]:
        now = time.monotonic()
        if self._cached_at is not None and (now - self._cached_at) < self._ttl_seconds:
            return self._cached_users
        users = await self._fetch_authorized_users()
        self._cached_users = users
        self._cached_at = now
        return users

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

    return frozenset(_normalize_username(u) for u in users)


def _normalize_username(username: str) -> str:
    """Normalise selon la convention MediaWiki (première lettre en majuscule, underscores
    équivalents à des espaces) pour que la comparaison ne dépende pas du format exact saisi."""
    username = username.strip().replace("_", " ")
    return username[:1].upper() + username[1:] if username else username
