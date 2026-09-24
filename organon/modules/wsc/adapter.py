"""Network access to the World Spider Catalog (WSC, NMBE).

Download and cache the public daily CSV export (no key required, unlike
the official REST API; see `db_inventory.yaml`, id: wsc). The file is
republished daily under a dated name (`species_export_YYYYMMDD.csv`):
today's date (UTC) is tried first, yesterday's as a fallback.

License CC BY-NC-SA 4.0: non-commercial, attribution required; see
`WscModule` (`can_render_external_link=False`, no public citation link).

The index is rebuilt once a day (UTC) at the first call needing it, not
at import: about 7.8 MB of CSV need not be downloaded by a deployment
that never queries this module.
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import UTC, datetime, timedelta

import httpx

from organon.core.http import OwnedClientMixin

BASE_URL = "https://wsc.nmbe.ch/resources/species_export_{date}.csv"
_DATE_ATTEMPTS = 2  # today (UTC), then yesterday if not republished yet


class WscAdapter(OwnedClientMixin):
    """WSC export client with a daily index."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client)
        self._by_name: dict[str, dict] | None = None
        self._cached_date: str | None = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        """Load the index if not already built today."""
        today = datetime.now(UTC).strftime("%Y%m%d")
        if self._cached_date == today:
            return
        async with self._lock:
            if self._cached_date == today:
                return
            rows = await self._download(today)
            if rows is None:
                # download failed: keep the previous index (even stale)
                # rather than lose everything
                return
            by_name: dict[str, dict] = {}
            for row in rows:
                if not row.get("speciesId"):
                    continue
                genus, species = row.get("genus"), row.get("species")
                if not genus or not species:
                    continue
                subspecies = row.get("subspecies")
                if subspecies:
                    # Never write the binomial key here: a subspecies
                    # row must not overwrite the parent species row
                    # (same genus and species) already indexed under it,
                    # or a binomial search would land on the subspecies.
                    by_name[f"{genus} {species} {subspecies}"] = row
                else:
                    by_name[f"{genus} {species}"] = row
            self._by_name = by_name
            self._cached_date = today

    async def _download(self, today: str) -> list[dict] | None:
        """Download the export of `today`, else of the day before."""
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
        """Return the row of an exact name, or None."""
        await self._ensure_loaded()
        if self._by_name is None:
            return None
        return self._by_name.get(name)
