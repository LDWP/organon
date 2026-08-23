"""Couche d'accès réseau pour Catalogue of Life (checklistbank.org) : appels HTTP et décodage
JSON bruts uniquement.

`3LR` est l'alias ChecklistBank pour la dernière release publiée du projet CoL (dataset n°3,
`alias: "COL"`, `version: "project"` sur `GET /dataset/3`) — utilisé ici en constante, sans
étape de découverte, à l'image de `DATASET_KEY` en dur dans `organon/modules/gbif/adapter.py`.
Interroger le dataset "3" (projet, copie de travail continuellement éditée) au lieu de "3LR"
renvoie des `id` internes à cette copie de travail, différents des identifiants stables publiés
sur catalogueoflife.org/data/taxon/{id} (résolus contre la dernière release, pas le projet).

Non utilisé par `organon.modules.col.module` (qui interroge `3LXR` via
`organon.modules.col_xr.adapter`, un sur-ensemble compatible) — conservé par précaution comme
retour en arrière possible plutôt que supprimé, voir la docstring de module.py."""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://api.checklistbank.org"
DATASET_ID = "3LR"  # dernière release publiée du projet "COL" (permanent, sans découverte)


class ColAdapter(OwnedClientMixin):
    async def search(self, taxon: str) -> dict | None:
        return await fetch_json(
            self._client,
            f"{API_BASE}/dataset/{DATASET_ID}/nameusage/search",
            params={
                "limit": 50,
                "offset": 0,
                "q": taxon,
                "sortBy": "taxonomic",
                "status": "_NOT_NULL",
                "type": "EXACT",
            },
        )
