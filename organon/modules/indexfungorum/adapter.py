"""Network access to Index Fungorum (indexfungorum.org).

Raw GET calls on the service's `HttpGet` binding (no SOAP envelope) and
raw XML decoding. ASP.NET encodes spaces in tag names as `_x0020_`,
decoded here to `_`. A "not found" answer is an empty `<NewDataSet />`
with HTTP 200.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from organon.core.http import OwnedClientMixin

BASE_URL = "https://www.indexfungorum.org/ixfwebservice/fungus.asmx"


def _decode_tag(tag: str) -> str:
    """Decode the `_x0020_` spaces of a tag name."""
    return tag.replace("_x0020_", "_")


def _parse_records(xml_text: str) -> list[dict[str, str]]:
    """Parse the XML records into dicts."""
    root = ET.fromstring(xml_text)
    return [{_decode_tag(field.tag): (field.text or "") for field in record} for record in root]


class IndexFungorumAdapter(OwnedClientMixin):
    """Raw Index Fungorum client."""

    async def name_search(self, text: str, max_number: int = 50) -> list[dict[str, str]]:
        """Search names by prefix.

        `AnywhereInText=false` filters by prefix server-side, not by
        equality: the caller must filter on `NAME_OF_FUNGUS`.
        """
        resp = await self._client.get(
            f"{BASE_URL}/NameSearch",
            params={"SearchText": text, "AnywhereInText": "false", "MaxNumber": max_number},
        )
        resp.raise_for_status()
        return _parse_records(resp.text)

    async def name_by_key(self, key: str) -> dict[str, str] | None:
        """Return the full record of a key, or None.

        Unlike `name_search`, it carries the publication fields and, for
        genus rank and below, the joined classification chain.
        """
        resp = await self._client.get(f"{BASE_URL}/NameByKey", params={"NameKey": key})
        resp.raise_for_status()
        records = _parse_records(resp.text)
        return records[0] if records else None

    async def names_by_current_key(self, key: str) -> list[dict[str, str]]:
        """Return all records whose current name is `key`.

        A real list of synonyms and basionyms of the accepted name. Not
        paginated by the service.
        """
        resp = await self._client.get(f"{BASE_URL}/NamesByCurrentKey", params={"CurrentKey": key})
        resp.raise_for_status()
        return _parse_records(resp.text)
