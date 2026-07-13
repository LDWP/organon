"""Couche d'accès réseau pour POWO (Plants of the World Online) : passe exclusivement par la
bibliothèque officielle `pykew` (https://github.com/RBGKew/pykew), jamais par un appel HTTP
direct à powo.science.kew.org. `pykew.powo.search`/`lookup` sont synchrones (basés sur
`requests`) : chaque appel est déporté sur un thread via `asyncio.to_thread` pour ne pas bloquer
la boucle événementielle.

`pykew.powo.lookup` ne lève pas d'exception sur un identifiant inconnu : l'API POWO répond alors
HTTP 404 avec un corps JSON `{"error": "Not Found"}` (vérifié en direct), que `Api.get(...).json()`
décode sans broncher (pas de `raise_for_status`). C'est donc `lookup()` ci-dessous qui détecte ce
cas via la clé `"error"`, plutôt que par exception.

Deux défauts corrigés en place sur l'objet `pykew.powo.API`, plutôt que dupliqués (interdit par
la consigne « toujours passer par pykew ») :

1. `Api.get` : `pykew` 0.1.3 appelle `requests.get(url)` sans aucun en-tête. Le WAF devant
   powo.science.kew.org (Azure Application Gateway) bloque ce client avec un 403 HTML dès lors
   que le `User-Agent` n'a pas une forme de navigateur — la page d'erreur HTML fait alors
   échouer `response.json()` dans pykew avec `JSONDecodeError` (vérifié en direct : un
   `requests.get` nu renvoie 403, le même appel avec un `User-Agent` de navigateur renvoie
   200/JSON). `_get_with_browser_headers` corrige `pykew.core.Api.get` en place pour y ajouter
   ces en-têtes (et un timeout, absent de l'original).

2. `POWO_URL` : la constante codée en dur dans pykew pointe vers l'ancien domaine
   `www.plantsoftheworldonline.org`, qui redirige (301 x2) vers `powo.science.kew.org` — mais
   **cette redirection perd la query string en route** (vérifié en direct : `resp.history` montre
   les paramètres présents jusqu'à l'avant-dernier saut, absents de `resp.url` final), si bien
   que toute recherche retombe silencieusement sur un browse-all non filtré (`totalResults`
   dans les millions) au lieu du résultat attendu. `_patch_pykew_base_url` réécrit `API._base_url`
   pour cibler directement `powo.science.kew.org`, sans passer par le domaine cassé.

Les deux correctifs sont appliqués une fois à l'import de ce module.

Throttling : aucun mécanisme de rate limiting mutualisé n'existe dans `organon/core` (vérifié :
aucun autre module n'en a besoin, chacun appelant `httpx` directement sans contrainte de débit
documentée côté source tierce). Kew recommande de rester sous ~5 req/s côté POWO : `_throttle`
impose un intervalle minimal entre appels via un verrou asyncio partagé au niveau du module."""

from __future__ import annotations

import asyncio
import itertools
import time

import pykew.core as pykew_core
import pykew.powo as powo
import requests

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _get_with_browser_headers(
    self: pykew_core.Api, method: str, params: dict | None = None
) -> requests.Response:
    resp = requests.get(self._url(method, params or {}), headers=_BROWSER_HEADERS, timeout=30)
    if resp.status_code == 249:  # trop de requêtes : pykew retente après 5s
        time.sleep(5)
        return self.get(method, params)
    return resp


_POWO_BASE_URL = "https://powo.science.kew.org/api/2"


def _patch_pykew_headers() -> None:
    if pykew_core.Api.get is not _get_with_browser_headers:
        pykew_core.Api.get = _get_with_browser_headers  # type: ignore[method-assign]


def _patch_pykew_base_url() -> None:
    powo.API._base_url = _POWO_BASE_URL


_patch_pykew_headers()
_patch_pykew_base_url()

MAX_RESULTS = 50
"""Borne le nombre de résultats matérialisés depuis `SearchResult` (pagination interne pykew de
500 éléments/page) : largement suffisant pour filtrer sur une correspondance exacte de nom, sans
matérialiser une page entière pour une requête à faible sélectivité."""

_MIN_INTERVAL = 0.2  # ~5 requêtes/s

_last_call = 0.0
_lock = asyncio.Lock()


async def _throttle() -> None:
    global _last_call
    async with _lock:
        wait = _last_call + _MIN_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


def _do_search(query: str) -> list[dict]:
    results = powo.search(query)
    if results.size() == 0:
        return []
    return list(itertools.islice(results, MAX_RESULTS))


def _do_lookup(taxon_id: str, include: list[str] | None) -> dict:
    return powo.lookup(taxon_id, include=include)


class PowoAdapter:
    async def search(self, name: str) -> list[dict]:
        await _throttle()
        try:
            return await asyncio.to_thread(_do_search, name)
        except requests.exceptions.RequestException:
            return []

    async def lookup(self, taxon_id: str, include: list[str] | None = None) -> dict | None:
        await _throttle()
        try:
            result = await asyncio.to_thread(_do_lookup, taxon_id, include)
        except requests.exceptions.RequestException:
            return None
        if not isinstance(result, dict) or "error" in result:
            return None
        return result
