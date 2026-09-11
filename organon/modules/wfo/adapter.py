"""Couche d'accès réseau pour World Flora Online (worldfloraonline.org) : aucune API
structurée trouvée (recherche confirmée en sondage direct), scraping HTML de la page de
résultats de recherche par expression régulière ciblée — même approche que
`organon.modules.eflora`.

Le paramètre `limit` de `/search` est respecté au-delà de sa valeur par défaut (24, vérifié
en direct jusqu'à 100) : demandé ici à 100 pour limiter le risque de rater un homonyme classé
au-delà de la première page plutôt que de paginer.

`ancestors()` (mode classification uniquement) récupère la chaîne d'ancêtres depuis la fiche
détail (`#taxonHierarchy`, voir `organon.modules.wfo.ranks` pour l'attribution des rangs).
Au-delà d'une certaine profondeur, la page replie les rangs supérieurs derrière un lien
« N higher taxa » pointant vers la page du premier ancêtre visible (vérifié en direct sur une
espèce : règne/sous-règne/embranchement repliés) — `ancestors()` suit ce lien jusqu'à
`MAX_ANCESTOR_HOPS` fois, la page de l'ancêtre visé n'étant en général plus repliée (vérifié :
une fiche de rang famille, moins profonde, ne replie jamais sa propre chaîne)."""

from __future__ import annotations

import html
import re

from organon.core.http import OwnedClientMixin

BASE_URL = "https://www.worldfloraonline.org"

# Chaque ligne de résultat associe un lien `/taxon/wfo-<id>` à son nom (attribut `title`,
# sans auteur), l'auteur affiché à part dans le même bloc `<h4>`, un statut taxonomique
# explicite (`Accepted Name` / `Synonym of ...` / `Unchecked`) absent des autres modules
# botaniques scrapés (eFlora, Tropicos) — utilisé comme signal de désambiguïsation en aval —
# et le rang du taxon lui-même (`Rank:`, ex. "Species"/"Variety"/"Family").
_RESULT_RE = re.compile(
    r'<a title="(?P<nom>[^"]+)" href="/taxon/(?P<id>wfo-\d+);jsessionid=[^"]*" class="result">'
    r'<h4 class="h4Results">(?:<strong>)?<em>[^<]+</em>\s*(?P<auteur>[^<]*?)\s*'
    r'(?:</strong>)?</h4></a>'
    r'.*?<span id="entryStatus">(?P<statut>[^<]*)</span>'
    r'.*?<span id="entryRank">(?P<rang_brut>[^<]*)</span>',
    re.DOTALL,
)

_ANCESTOR_RE = re.compile(
    r'<a href="/taxon/(?P<id>wfo-\d+)[^"]*" class="ancestorsList"><em>(?P<nom>[^<]+)</em>'
    r'\s*(?P<auteur>[^<]*?)</a>'
)
_TRUNCATED_RE = re.compile(
    r'<a href="/taxon/(?P<id>wfo-\d+)[^"]*" class="ancestorsList">\s*\d+ higher taxa\s*</a>'
)

MAX_ANCESTOR_HOPS = 4
"""Borne le nombre de pages suivies pour désempiler le lien « N higher taxa » (voir docstring
du module) : la profondeur réelle d'une classification botanique (règne -> ... -> genre) ne
justifie jamais plus de quelques replis successifs."""


class WfoAdapter(OwnedClientMixin):
    async def search(self, name: str) -> list[dict]:
        """Renvoie une liste de `{id, nom, auteur, statut, rang_brut}`, déjà nettoyée
        (entités HTML décodées) mais pas encore filtrée au nom recherché (laissé à
        module.py)."""
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
                    "rang_brut": html.unescape(m.group("rang_brut")).strip() or None,
                }
            )
        return out

    async def ancestors(self, wfo_id: str) -> list[dict]:
        """Renvoie la chaîne des ancêtres `{id, nom, auteur}`, triée du règne vers le parent
        le plus proche — sans le taxon lui-même (voir docstring du module pour le repli
        « N higher taxa »)."""
        chain: list[dict] = []
        seen: set[str] = set()
        current = wfo_id
        for _ in range(MAX_ANCESTOR_HOPS):
            resp = await self._client.get(f"{BASE_URL}/taxon/{current}")
            resp.raise_for_status()
            page = resp.text
            level = []
            for m in _ANCESTOR_RE.finditer(page):
                ancestor_id = m.group("id")
                if ancestor_id in seen:
                    continue
                seen.add(ancestor_id)
                level.append(
                    {
                        "id": ancestor_id,
                        "nom": html.unescape(m.group("nom")).strip(),
                        "auteur": html.unescape(m.group("auteur")).strip() or None,
                    }
                )
            chain = level + chain
            truncated = _TRUNCATED_RE.search(page)
            if not truncated:
                break
            current = truncated.group("id")
        return chain
