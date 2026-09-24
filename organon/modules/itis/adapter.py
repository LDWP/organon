"""Network access to ITIS: raw HTTP calls and XML parsing.

Uses `xml.etree.ElementTree` resolving tags by local name (ignoring the
`ax21:` or `ns:` namespace prefix). The chain of higher ranks comes from
`getFullHierarchyFromTSN` (one call), not one per level.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from organon.core.http import OwnedClientMixin

BASE_URL = "https://www.itis.gov/ITISWebService/services/ITISService"


def _local(elem: ET.Element, tag: str) -> ET.Element | None:
    """Return the first descendant with the given local tag name."""
    for child in elem.iter():
        if child.tag.rsplit("}", 1)[-1] == tag:
            return child
    return None


def _local_all(elem: ET.Element, tag: str) -> list[ET.Element]:
    """Return all descendants with the given local tag name."""
    return [child for child in elem.iter() if child.tag.rsplit("}", 1)[-1] == tag]


def _text(elem: ET.Element | None) -> str | None:
    """Return the stripped text of an element, or None if empty."""
    if elem is None or elem.text is None:
        return None
    text = elem.text.strip()
    return text or None


class ItisAdapter(OwnedClientMixin):
    """Raw ITIS web service client."""

    async def _get_xml(self, endpoint: str, tsn: int | str | None = None, **params) -> ET.Element:
        """GET an endpoint and parse its XML."""
        if tsn is not None:
            params["tsn"] = tsn
        resp = await self._client.get(f"{BASE_URL}/{endpoint}", params=params)
        resp.raise_for_status()
        if not resp.content:
            # ITIS sometimes answers 200 with an empty body
            # (historically unstable service): an empty element makes
            # `_local` and `_local_all` yield nothing, like any absent
            # result, consistent with the `empty_value` fallback of
            # fetch_json.
            return ET.Element("empty")
        return ET.fromstring(resp.text)

    async def search_by_scientific_name(self, name: str) -> list[dict]:
        """Return the names matching a search key."""
        root = await self._get_xml("searchByScientificName", srchKey=name)
        return [
            {
                "tsn": _text(_local(el, "tsn")),
                "author": _text(_local(el, "author")),
                "combinedName": _text(_local(el, "combinedName")),
                "kingdom": _text(_local(el, "kingdom")),
            }
            for el in _local_all(root, "scientificNames")
        ]

    async def rank_name(self, tsn: int | str) -> str | None:
        """Return the rank name of a TSN."""
        root = await self._get_xml("getTaxonomicRankNameFromTSN", tsn)
        return _text(_local(root, "rankName"))

    async def scientific_name(self, tsn: int | str) -> str | None:
        """Return the scientific name of a TSN."""
        root = await self._get_xml("getScientificNameFromTSN", tsn)
        return _text(_local(root, "combinedName"))

    async def authorship(self, tsn: int | str) -> str | None:
        """Return the authorship of a TSN."""
        root = await self._get_xml("getTaxonAuthorshipFromTSN", tsn)
        return _text(_local(root, "authorship"))

    async def accepted_names(self, tsn: int | str) -> list[dict]:
        """Return the accepted names of a TSN (set for a synonym)."""
        root = await self._get_xml("getAcceptedNamesFromTSN", tsn)
        names = []
        for el in root.iter():
            if (
                el.tag.rsplit("}", 1)[-1] == "acceptedNames"
                and el.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") != "true"
            ):
                names.append(
                    {
                        "acceptedName": _text(_local(el, "acceptedName")),
                        "acceptedTsn": _text(_local(el, "acceptedTsn")),
                    }
                )
        return names

    async def full_hierarchy(self, tsn: int | str) -> list[dict]:
        """Return the full hierarchy of a TSN, root first."""
        root = await self._get_xml("getFullHierarchyFromTSN", tsn)
        return [
            {
                "tsn": _text(_local(el, "tsn")),
                "author": _text(_local(el, "author")),
                "rankName": _text(_local(el, "rankName")),
                "taxonName": _text(_local(el, "taxonName")),
            }
            for el in _local_all(root, "hierarchyList")
        ]

    async def hierarchy_down(self, tsn: int | str) -> list[dict]:
        """Return the direct children of a TSN."""
        root = await self._get_xml("getHierarchyDownFromTSN", tsn)
        out = []
        for el in _local_all(root, "hierarchyList"):
            if el.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                continue
            out.append(
                {
                    "taxonName": _text(_local(el, "taxonName")),
                    "author": _text(_local(el, "author")),
                    "rankName": _text(_local(el, "rankName")),
                }
            )
        return out

    async def synonym_names(self, tsn: int | str) -> list[dict]:
        """Return the synonyms of a TSN."""
        root = await self._get_xml("getSynonymNamesFromTSN", tsn)
        out = []
        for el in _local_all(root, "synonyms"):
            if el.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                continue
            sci_name = _text(_local(el, "sciName"))
            if sci_name is None:
                continue
            out.append({"sciName": sci_name, "author": _text(_local(el, "author"))})
        return out

    async def common_names(self, tsn: int | str) -> list[dict]:
        """Return the common names of a TSN."""
        root = await self._get_xml("getCommonNamesFromTSN", tsn)
        out = []
        for el in _local_all(root, "commonNames"):
            if el.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                continue
            out.append(
                {
                    "language": _text(_local(el, "language")),
                    "commonName": _text(_local(el, "commonName")),
                }
            )
        return out
