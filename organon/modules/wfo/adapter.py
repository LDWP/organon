"""Couche d'accès réseau pour World Flora Online (worldfloraonline.org) : aucune API
structurée trouvée (recherche confirmée en sondage direct), scraping HTML de la page de
résultats de recherche par expression régulière ciblée — même approche que
`organon.modules.eflora`.

Le paramètre `limit` de `/search` est respecté au-delà de sa valeur par défaut (24, vérifié
en direct jusqu'à 100) : demandé ici à 100 pour limiter le risque de rater un homonyme classé
au-delà de la première page plutôt que de paginer."""

from __future__ import annotations

import html
import re

import httpx

BASE_URL = "https://www.worldfloraonline.org"

# Chaque ligne de résultat associe un lien `/taxon/wfo-<id>` à son nom (attribut `title`,
# sans auteur), l'auteur affiché à part dans le même bloc `<h4>`, et un statut taxonomique
# explicite (`Accepted Name` / `Synonym of ...` / `Unchecked`) absent des autres modules
# botaniques scrapés (eFlora, Tropicos) — utilisé comme signal de désambiguïsation en aval.
_RESULT_RE = re.compile(
    r'<a title="(?P<nom>[^"]+)" href="/taxon/(?P<id>wfo-\d+);jsessionid=[^"]*" class="result">'
    r'<h4 class="h4Results">(?:<strong>)?<em>[^<]+</em>\s*(?P<auteur>[^<]*?)\s*(?:</strong>)?</h4></a>'
    r'.*?<span id="entryStatus">(?P<statut>[^<]*)</span>',
    re.DOTALL,
)


class WfoAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        """Renvoie une liste de `{id, nom, auteur, statut}`, déjà nettoyée (entités HTML
        décodées) mais pas encore filtrée au nom recherché (laissé à module.py)."""
        resp = await self._client.get(f"{BASE_URL}/search", params={"query": name, "limit": 100})
        resp.raise_for_status()
        out = []
        for m in _RESULT_RE.finditer(resp.text):
            out.append(
                {
                    "id": m.group("id"),
                    "nom": html.unescape(m.group("nom")).strip(),
                    "auteur": html.unescape(m.group("auteur")).strip() or None,
                    "statut": html.unescape(m.group("statut")).strip(),
                }
            )
        return out
