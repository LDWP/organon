"""Network access to TPDB (Paleobiology Database, `paleobiodb.org`).

Raw HTTP and JSON only. `vocab=pbdb` is used everywhere for explicit
field names (`taxon_rank`, `taxon_attr`…) rather than the compact
two-letter codes of the default mode, avoiding a table of numeric rank
codes besides the translation table to French.
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin, fetch_json

API_BASE = "https://paleobiodb.org/data1.2"


class TpdbAdapter(OwnedClientMixin):
    """Raw PBDB API client."""

    async def search(self, name: str) -> list[dict]:
        """Return the PBDB records matching a name."""
        data = await fetch_json(
            self._client,
            f"{API_BASE}/combined/auto.json",
            params={"name": name, "type": "cls", "vocab": "pbdb"},
            empty_value={},
        )
        return data.get("records", [])

    async def taxon_by_name(self, name: str) -> dict | None:
        """Return the PBDB record of a taxon name, or None.

        Deliberately a search by *name*, not by `id=txn:{orig_no}`: an
        id query always returns the currently accepted name (e.g.
        `id=txn:451494` returns "Ptelea modesta" although 451494 is the
        original combination "Cytisus modestus"), which would prevent
        getting the author of the requested combination.
        """
        data = await fetch_json(
            self._client,
            f"{API_BASE}/taxa/single.json",
            params={"name": name, "vocab": "pbdb", "show": "attr"},
            empty_value={},
        )
        records = data.get("records", [])
        return records[0] if records else None
