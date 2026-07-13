"""Couche d'accès réseau pour eFloras.org (Flora of North America/China/Pakistan, hébergées sur
la même plateforme) : aucune API structurée trouvée, une même espèce peut avoir une fiche
distincte par flore régionale (`flora_id`) sur la page de résultats de recherche, extraite ici
par expression régulière ciblée plutôt qu'un découpage positionnel fragile."""

from __future__ import annotations

import re

import httpx

BASE_URL = "http://www.efloras.org"

# 1 = Flora of North America, 2 = Flora of China, 5 = Flora of Pakistan — les seules flores
# dont la couverture est jugée fiable pour ce module.
VALID_FLORA_IDS = {1, 2, 5}

_RESULT_RE = re.compile(r"florataxon\.aspx\?flora_id=(\d+)&taxon_id=(\d+)'[^>]*>\s*<b>([^<]+)</b>")


class EfloraAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[tuple[int, int, str]]:
        """Renvoie une liste de `(flora_id, taxon_id, nom_affiché)`, déjà filtrée aux flores
        valides mais pas encore au nom recherché (laissé à module.py)."""
        resp = await self._client.get(f"{BASE_URL}/browse.aspx", params={"flora_id": 0, "name_str": name})
        resp.raise_for_status()
        out = []
        for fid_s, tid_s, nom in _RESULT_RE.findall(resp.text):
            fid = int(fid_s)
            if fid in VALID_FLORA_IDS:
                out.append((fid, int(tid_s), nom.strip()))
        return out
