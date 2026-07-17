"""Couche d'accès réseau pour ITIS : appels HTTP et parsing XML bruts uniquement. Utilise
`xml.etree.ElementTree` avec une résolution de balise par nom local (ignore le préfixe d'espace
de noms `ax21:`/`ns:`), adapté au XML bien formé renvoyé par ce service. La chaîne des rangs
supérieurs est récupérée via `getFullHierarchyFromTSN` (un seul appel), pas un appel par niveau
taxonomique."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx

BASE_URL = "https://www.itis.gov/ITISWebService/services/ITISService"


def _local(elem: ET.Element, tag: str) -> ET.Element | None:
    for child in elem.iter():
        if child.tag.rsplit("}", 1)[-1] == tag:
            return child
    return None


def _local_all(elem: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in elem.iter() if child.tag.rsplit("}", 1)[-1] == tag]


def _text(elem: ET.Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    text = elem.text.strip()
    return text or None


class ItisAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_xml(self, endpoint: str, tsn: int | str | None = None, **params) -> ET.Element:
        if tsn is not None:
            params["tsn"] = tsn
        resp = await self._client.get(f"{BASE_URL}/{endpoint}", params=params)
        resp.raise_for_status()
        return ET.fromstring(resp.text)

    async def search_by_scientific_name(self, name: str) -> list[dict]:
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
        root = await self._get_xml("getTaxonomicRankNameFromTSN", tsn)
        return _text(_local(root, "rankName"))

    async def scientific_name(self, tsn: int | str) -> str | None:
        root = await self._get_xml("getScientificNameFromTSN", tsn)
        return _text(_local(root, "combinedName"))

    async def authorship(self, tsn: int | str) -> str | None:
        root = await self._get_xml("getTaxonAuthorshipFromTSN", tsn)
        return _text(_local(root, "authorship"))

    async def accepted_names(self, tsn: int | str) -> list[dict]:
        root = await self._get_xml("getAcceptedNamesFromTSN", tsn)
        names = []
        for el in root.iter():
            if el.tag.rsplit("}", 1)[-1] == "acceptedNames" and el.attrib.get(
                "{http://www.w3.org/2001/XMLSchema-instance}nil"
            ) != "true":
                names.append(
                    {
                        "acceptedName": _text(_local(el, "acceptedName")),
                        "acceptedTsn": _text(_local(el, "acceptedTsn")),
                    }
                )
        return names

    async def full_hierarchy(self, tsn: int | str) -> list[dict]:
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
        root = await self._get_xml("getCommonNamesFromTSN", tsn)
        out = []
        for el in _local_all(root, "commonNames"):
            if el.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                continue
            out.append({"language": _text(_local(el, "language")), "commonName": _text(_local(el, "commonName"))})
        return out
