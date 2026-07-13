"""Couche d'accès réseau pour l'EPPO Global Database (gd.eppo.int, organisation européenne et
méditerranéenne pour la protection des plantes). La recherche (`search()`) passe par le vrai
point d'entrée JSON que le site utilise lui-même pour son autocomplétion. La fiche détaillée
d'un taxon (`taxon_detail()`) n'a en revanche aucun équivalent JSON trouvé (sondé en direct) :
seule la page HTML existe, d'où une extraction ciblée par expression régulière ici plutôt
qu'un décodage JSON — limitée à l'autorité et aux noms vernaculaires français, les deux seuls
champs consommés par module.py."""

from __future__ import annotations

import html
import re

import httpx

BASE_URL = "https://gd.eppo.int"

_AUTHORITY_RE = re.compile(r"<strong>Authority:</strong>\s*([^<]+?)\s*</li>")
_FRENCH_ROW_RE = re.compile(
    r"<tr>\s*<td>([^<]+)</td>\s*<td class=\"text-center\">French[^<]*</td>\s*</tr>"
)


class OeppAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/ajax/search", params={"k": name, "s": 1, "m": 1, "t": 0, "l": ""}
        )
        resp.raise_for_status()
        return resp.json() or []

    async def taxon_detail(self, eppo_code: str) -> dict:
        """Renvoie `{"auteur": str | None, "vernaculaire_fr": list[str]}` — jamais None : une
        page introuvable/vide donne simplement des champs vides plutôt que de faire échouer
        tout le module (l'identifiant reste utilisable même sans ces détails)."""
        resp = await self._client.get(f"{BASE_URL}/taxon/{eppo_code}")
        if resp.status_code >= 400:
            return {"auteur": None, "vernaculaire_fr": []}
        text = resp.text

        auteur = None
        m = _AUTHORITY_RE.search(text)
        if m:
            auteur = html.unescape(m.group(1)).strip() or None

        vernaculaire = [html.unescape(m.group(1)).strip() for m in _FRENCH_ROW_RE.finditer(text)]

        return {"auteur": auteur, "vernaculaire_fr": vernaculaire}
