"""Couche d'accès réseau pour TPDB (Paleobiology Database, `paleobiodb.org/data1.2`) : appels
HTTP et décodage JSON bruts uniquement. `vocab=pbdb` est utilisé partout pour obtenir des noms
de champs explicites (`taxon_rank`, `taxon_attr`…) plutôt que les codes compacts à deux lettres
du mode par défaut (`rnk`, `att`…), évitant une table de correspondance de codes numériques de
rang en plus de la table de traduction vers le français."""

from __future__ import annotations

import httpx

API_BASE = "https://paleobiodb.org/data1.2"


class TpdbAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[dict]:
        resp = await self._client.get(
            f"{API_BASE}/combined/auto.json", params={"name": name, "type": "cls", "vocab": "pbdb"}
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("records", [])

    async def taxon_by_name(self, name: str) -> dict | None:
        """Note : volontairement une recherche par *nom* et non par `id=txn:{orig_no}` — testé
        en direct, une requête par id renvoie systématiquement le nom actuellement accepté
        (ex. `id=txn:451494` renvoie "Ptelea modesta" même si 451494 est l'identifiant du
        combinaison originale "Cytisus modestus") plutôt que la combinaison précise recherchée,
        ce qui empêcherait de récupérer l'auteur propre à l'orthographe/combinaison demandée."""
        resp = await self._client.get(
            f"{API_BASE}/taxa/single.json",
            params={"name": name, "vocab": "pbdb", "show": "attr"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        records = resp.json().get("records", [])
        return records[0] if records else None
