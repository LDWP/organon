"""Couche d'accès réseau pour TPDB (Paleobiology Database, `paleobiodb.org/data1.2`) : appels
HTTP et décodage JSON bruts uniquement. `vocab=pbdb` est utilisé partout pour obtenir des noms
de champs explicites (`taxon_rank`, `taxon_attr`…) plutôt que les codes compacts à deux lettres
du mode par défaut (`rnk`, `att`…), évitant une table de correspondance de codes numériques de
rang en plus de la table de traduction vers le français."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://paleobiodb.org/data1.2"


class TpdbAdapter(OwnedClientMixin):
    async def search(self, name: str) -> list[dict]:
        data = await fetch_json(
            self._client,
            f"{API_BASE}/combined/auto.json",
            params={"name": name, "type": "cls", "vocab": "pbdb"},
            empty_value={},
        )
        return data.get("records", [])

    async def taxon_by_name(self, name: str) -> dict | None:
        """Note : volontairement une recherche par *nom* et non par `id=txn:{orig_no}` — testé
        en direct, une requête par id renvoie systématiquement le nom actuellement accepté
        (ex. `id=txn:451494` renvoie "Ptelea modesta" même si 451494 est l'identifiant du
        combinaison originale "Cytisus modestus") plutôt que la combinaison précise recherchée,
        ce qui empêcherait de récupérer l'auteur propre à l'orthographe/combinaison demandée."""
        data = await fetch_json(
            self._client,
            f"{API_BASE}/taxa/single.json",
            params={"name": name, "vocab": "pbdb", "show": "attr"},
            empty_value={},
        )
        records = data.get("records", [])
        return records[0] if records else None
