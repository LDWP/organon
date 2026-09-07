"""Adaptateur fr.wikipedia.org : lit le wikitexte de l'article d'un taxon (famille/ordre/classe,
voir module.py) et en extrait le(s) portail(s) déjà déclaré(s) via `{{Portail|...}}`, plutôt que
de deviner à partir des catégories cachées rendues sur la page (qui incluent les portails
"parents" par cascade — ex. l'article Falconidae ne déclare que `{{Portail|ornithologie}}` mais
affiche aussi Zoologie/Biologie/Sciences par cascade de catégories, vérifié en direct).

`redirects=1` : les noms scientifiques de rang classe/ordre redirigent très souvent vers le nom
vernaculaire (ex. Aves -> Oiseau, Insecta -> Insecte, vérifié en direct) ; sans ce paramètre,
`prop=revisions` renverrait le contenu de la page de redirection elle-même (une ligne
`#REDIRECT [[...]]`), jamais celui de la cible.

Édition fr uniquement pour l'instant ; d'autres méthodes (catégories, ébauches, existence de
page) rejoindront cet adaptateur au fil de l'eau — voir module.py."""

from __future__ import annotations

import re

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin

API_URL = "https://fr.wikipedia.org/w/api.php"

_PORTAIL_RE = re.compile(r"\{\{\s*[Pp]ortail\s*\|([^}]+)\}\}")


def _extrait_portails(wikitext: str) -> list[str]:
    match = _PORTAIL_RE.search(wikitext)
    if not match:
        return []
    return [p.strip() for p in match.group(1).split("|") if p.strip()]


class WikipediaAdapter(OwnedClientMixin):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def portails(self, titre: str) -> list[str] | None:
        """Portail(s) déclaré(s) par l'article `titre` (en suivant une éventuelle redirection),
        ou None si la page n'existe pas ou ne déclare aucun `{{Portail}}`."""
        params = {
            "action": "query",
            "titles": titre,
            "redirects": "1",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "formatversion": "2",
            "format": "json",
        }
        resp = await self._client.get(API_URL, params=params)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages") or []
        if not pages or pages[0].get("missing"):
            return None
        revisions = pages[0].get("revisions")
        if not revisions:
            return None
        wikitext = revisions[0]["slots"]["main"]["content"]
        return _extrait_portails(wikitext) or None
