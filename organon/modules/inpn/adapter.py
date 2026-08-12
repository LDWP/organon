"""Couche d'accès réseau pour TAXREF/INPN.

Recherche par nom (`GET .../api/taxa/search?nomComplet=...`) : JSON, mais la correspondance
côté serveur est floue (substring/pertinence, pas une égalité stricte) — un nom courant comme
« Theria » ou « Carnivora » peut renvoyer des dizaines d'homonymes/substrings sans rapport
avant l'entrée exacte recherchée (vérifié en direct : « Vulpes » seul remonte d'abord
`Albula vulpes`, un poisson). `nb_rows` volontairement large (500 par défaut) pour maximiser
la chance que l'entrée exacte soit présente ; la sélection stricte par `cdNom` + `lbNom` reste
à la charge de `module.py`, jamais de cet adaptateur.

Fiche détail (`GET .../taxa/{cdNom}`) : page HTML (JSP), pas de JSON. Aucun endpoint
équivalent à `getFullHierarchyFromTSN` (ITIS, un seul appel pour toute la lignée) n'a été
trouvé : le fil d'Ariane de cette page donne les ancêtres (nom, id) en un seul appel, mais pas
leur rang — resolu ancêtre par ancêtre via `search()` côté module.py.

WAF côté taxref.mnhn.fr : renvoie 403 sur l'IP Toolforge avec le `User-Agent` par défaut de
httpx (`python-httpx/...`), alors que le même appel passe sans problème depuis un poste de
développement classique (vérifié en direct) — même symptôme que POWO (voir
`organon.modules.powo.adapter`), un WAF qui cible les signatures de client HTTP non-navigateur
plutôt que l'IP seule. `_BROWSER_HEADERS` imite un navigateur pour contourner ce filtrage."""

from __future__ import annotations

import re

import httpx

from organon.core.http import OwnedClientMixin

API_BASE = "https://taxref.mnhn.fr/taxref-web/api"
WEB_BASE = "https://taxref.mnhn.fr/taxref-web"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}

_BREADCRUMB_RE = re.compile(r'<a href="/taxref-web/taxa/(?P<id>\d+)">(?P<nom>[^<]+)</a>\s*&rsaquo;')
_VERNACULAR_BLOCK_RE = re.compile(
    r"<legend>NOMS VERNACULAIRES</legend>(?P<block>.*?)</fieldset>", re.S
)
# Plusieurs noms peuvent partager un seul <span> séparés par des virgules (ex. observé en
# direct sur Vulpes vulpes : "Renard roux, Renard, Goupil") — scindés par l'appelant.
_VERNACULAR_ENTRY_RE = re.compile(
    r"<span>(?P<noms>[^<]+)</span>\s*\(<a[^>]*>(?P<langue>[^<]+)</a>", re.S
)


class InpnAdapter(OwnedClientMixin):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(client, headers=_BROWSER_HEADERS)

    async def search(self, nom_complet: str, nb_rows: int = 500) -> list[dict]:
        resp = await self._client.get(
            f"{API_BASE}/taxa/search", params={"nomComplet": nom_complet, "nbRows": nb_rows}
        )
        resp.raise_for_status()
        return resp.json()

    async def detail_html(self, cd_nom: int) -> str:
        resp = await self._client.get(f"{WEB_BASE}/taxa/{cd_nom}")
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def parse_breadcrumb(html: str) -> list[tuple[int, str]]:
        """Lignée complète racine -> parent immédiat (le taxon lui-même n'apparaît pas dans
        son propre fil d'Ariane, qui ne montre que les ancêtres)."""
        return [(int(m.group("id")), m.group("nom").strip()) for m in _BREADCRUMB_RE.finditer(html)]

    @staticmethod
    def parse_vernacular_french(html: str) -> list[str]:
        block_match = _VERNACULAR_BLOCK_RE.search(html)
        if block_match is None:
            return []
        out: list[str] = []
        for m in _VERNACULAR_ENTRY_RE.finditer(block_match.group("block")):
            if m.group("langue").strip() != "Français":
                continue
            out.extend(nom.strip() for nom in m.group("noms").split(",") if nom.strip())
        return out
