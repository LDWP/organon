"""Couche d'accès réseau pour le World Spider Catalog (WSC, NMBE) : télécharge et met en cache
l'export CSV quotidien public (aucune clé requise, contrairement à l'API REST officielle qui en
exige une — voir organon/core/data/db_inventory.yaml, id: wsc). Le fichier est republié chaque
jour sous un nom daté (`species_export_YYYYMMDD.csv`) ; la date du jour (UTC) est essayée en
premier, la veille en repli si le fichier du jour n'est pas encore disponible.

Licence CC BY-NC-SA 4.0 (https://wsc.nmbe.ch/dataresources) : usage non commercial, attribution
requise — voir `organon.modules.wsc.module.WscModule` (can_render_external_link=False, aucun
lien de citation publique produit).

L'index est reconstruit une fois par jour (UTC) au premier appel qui le nécessite, pas à
l'import : ~7,8 Mo de CSV n'ont pas à être téléchargés pour un déploiement qui n'interroge
jamais ce module."""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = "https://wsc.nmbe.ch/resources/species_export_{date}.csv"
_DATE_ATTEMPTS = 2  # jour courant (UTC), puis veille si pas encore republié


class WscAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._by_name: dict[str, dict] | None = None
        self._by_id: dict[str, dict] | None = None
        self._cached_date: str | None = None
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _ensure_loaded(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        if self._cached_date == today:
            return
        async with self._lock:
            if self._cached_date == today:
                return
            rows = await self._download(today)
            if rows is None:
                return  # échec de téléchargement : garde l'index précédent (même périmé) plutôt que de tout perdre
            by_name: dict[str, dict] = {}
            by_id: dict[str, dict] = {}
            for row in rows:
                species_id = row.get("speciesId")
                if not species_id:
                    continue
                by_id[species_id] = row
                genus, species = row.get("genus"), row.get("species")
                if not genus or not species:
                    continue
                subspecies = row.get("subspecies")
                if subspecies:
                    # Ne jamais écrire la clé binomiale ici : une ligne de sous-espèce ne doit
                    # pas écraser la ligne espèce-mère (même genus+species) déjà indexée sous
                    # cette clé, sans quoi une recherche sur le nom binomial retomberait sur la
                    # sous-espèce au lieu de l'espèce.
                    by_name[f"{genus} {species} {subspecies}"] = row
                else:
                    by_name[f"{genus} {species}"] = row
            self._by_name = by_name
            self._by_id = by_id
            self._cached_date = today

    async def _download(self, today: str) -> list[dict] | None:
        date = datetime.strptime(today, "%Y%m%d")
        for attempt in range(_DATE_ATTEMPTS):
            candidate = (date - timedelta(days=attempt)).strftime("%Y%m%d")
            resp = await self._client.get(BASE_URL.format(date=candidate))
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            return list(csv.DictReader(io.StringIO(resp.text)))
        return None

    async def search(self, name: str) -> dict | None:
        await self._ensure_loaded()
        if self._by_name is None:
            return None
        return self._by_name.get(name)

    async def by_id(self, species_id: str) -> dict | None:
        await self._ensure_loaded()
        if self._by_id is None:
            return None
        return self._by_id.get(species_id)
