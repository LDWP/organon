"""Couche d'accès réseau pour Index Fungorum (indexfungorum.org/ixfwebservice/fungus.asmx) :
appels HTTP bruts sur le binding `HttpGet` du service (une simple requête GET par URL, décrite
dans le WSDL à côté des bindings SOAP 1.1/1.2 — pas besoin de construire une enveloppe SOAP) et
décodage XML brut. Le service ASP.NET encode les espaces des noms de balise en `_x0020_` (ex.
`NAME_x0020_OF_x0020_FUNGUS`), décodés ici en `NAME_OF_FUNGUS` pour un accès plus lisible côté
module.py. Réponse "non trouvé" confirmée en direct : `<NewDataSet />` vide, HTTP 200 (jamais
d'erreur HTTP ni de 204)."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx

BASE_URL = "https://www.indexfungorum.org/ixfwebservice/fungus.asmx"


def _decode_tag(tag: str) -> str:
    return tag.replace("_x0020_", "_")


def _parse_records(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    return [{_decode_tag(field.tag): (field.text or "") for field in record} for record in root]


class IndexFungorumAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def name_search(self, text: str, max_number: int = 50) -> list[dict[str, str]]:
        """`AnywhereInText=false` filtre par préfixe côté serveur, pas par égalité stricte
        (vérifié en direct : une recherche "Amanita" renvoie aussi "Amanita muscaria...") — le
        filtrage par égalité exacte sur `NAME_OF_FUNGUS` reste à la charge de l'appelant."""
        resp = await self._client.get(
            f"{BASE_URL}/NameSearch",
            params={"SearchText": text, "AnywhereInText": "false", "MaxNumber": max_number},
        )
        resp.raise_for_status()
        return _parse_records(resp.text)

    async def name_by_key(self, key: str) -> dict[str, str] | None:
        """Contrairement à `name_search`, renvoie l'enregistrement complet : champs de
        publication et, pour les rangs genre et en dessous, la chaîne de classification jointe
        (`Genus_name`...`Kingdom_name` — voir ranks.py)."""
        resp = await self._client.get(f"{BASE_URL}/NameByKey", params={"NameKey": key})
        resp.raise_for_status()
        records = _parse_records(resp.text)
        return records[0] if records else None

    async def names_by_current_key(self, key: str) -> list[dict[str, str]]:
        """Recherche inverse : tous les enregistrements dont `CURRENT_NAME_RECORD_NUMBER`
        vaut `key` — une vraie liste de synonymes/basionymes pour le nom actuellement accepté
        `key`. Non paginé côté service (aucun paramètre offset dans le WSDL)."""
        resp = await self._client.get(f"{BASE_URL}/NamesByCurrentKey", params={"CurrentKey": key})
        resp.raise_for_status()
        return _parse_records(resp.text)
