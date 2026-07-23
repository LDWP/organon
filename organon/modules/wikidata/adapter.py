"""Couche d'accès en lecture à l'item Wikidata d'un taxon, via l'API d'action `wbgetentities`
(distincte du service SPARQL WDQS déjà utilisé par `organon.modules.externe.adapter` pour la
résolution nom -> QID : ici l'entrée est déjà un QID, obtenu depuis la recherche par item
Wikidata, voir `organon.api.routes.search`).

`EXTERNAL_ID_PROPERTIES` ne couvre que les propriétés vérifiées en direct sur
www.wikidata.org (voir recherches du 2026-07-24) : pas de propriété devinée de mémoire,
conformément à la rigueur attendue ailleurs dans le dépôt (ex.
organon/core/data/db_inventory.yaml, tout "vérifié en direct"). Modules Organon dont l'id de
propriété Wikidata reste à vérifier (absents ci-dessous par choix, pas par oubli) : algaebase,
reptile_database, vascan, eflora, telametro, wsc.
"""

from __future__ import annotations

from typing import Any

import httpx

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "Organon/0.1 (https://fr.wikipedia.org/wiki/Projet:Biologie/Taxobot)"

TAXON_NAME_PROPERTY = "P225"
AUTHOR_PROPERTY = "P405"
PUBLICATION_YEAR_PROPERTY = "P574"
PARENT_TAXON_PROPERTY = "P171"

# GBIF est en migration au 2026-07-24 : P846 ("GBIF-species-ID (before 2026 update)", ~3,3M
# d'utilisations, toujours majoritaire) et P14607 ("GBIF taxon ID", nouveau schéma, ~500
# utilisations) coexistent sur Wikidata. Les deux sont vérifiés donc les deux sont gardés, avec
# P14607 déclaré après P846 : à valeur présente des deux côtés sur un même item, la boucle de
# `external_ids()` doit retenir la nouvelle plutôt que l'ancienne.
EXTERNAL_ID_PROPERTIES: dict[str, str] = {
    "P846": "gbif",
    "P14607": "gbif",
    "P815": "itis",
    "P850": "wrms",
    "P961": "ipni",
    "P5037": "powo",
    "P1391": "indexfungorum",
    "P960": "tropicos",
    "P7715": "wfo",
    "P10585": "col",
    "P959": "msw",
    "P4024": "adw",
    "P11043": "hesperomys",
    "P10907": "tpdb",
    "P830": "eol",
    "P2040": "cites",
    "P685": "ncbi",
    "P3031": "oepp",
    "P5055": "irmng",
}


def _first_snak_value(claims: dict[str, Any], prop: str) -> Any | None:
    statements = claims.get(prop)
    if not statements:
        return None
    try:
        return statements[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None


class WikidataAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT})
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_entity(self, qid: str) -> dict[str, Any] | None:
        """Récupère claims + label français de l'item, ou None si le QID n'existe pas."""
        resp = await self._client.get(
            WIKIDATA_API_URL,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|labels",
                "languages": "fr",
                "format": "json",
            },
        )
        resp.raise_for_status()
        entity = resp.json().get("entities", {}).get(qid)
        if entity is None or "missing" in entity:
            return None
        return entity

    def taxon_name(self, entity: dict[str, Any]) -> str | None:
        value = _first_snak_value(entity.get("claims", {}), TAXON_NAME_PROPERTY)
        return value if isinstance(value, str) else None

    def external_ids(self, entity: dict[str, Any]) -> dict[str, str]:
        claims = entity.get("claims", {})
        ids: dict[str, str] = {}
        for prop, module_id in EXTERNAL_ID_PROPERTIES.items():
            value = _first_snak_value(claims, prop)
            if isinstance(value, str):
                ids[module_id] = value
        return ids

    def author_qid(self, entity: dict[str, Any]) -> str | None:
        value = _first_snak_value(entity.get("claims", {}), AUTHOR_PROPERTY)
        return value.get("id") if isinstance(value, dict) else None

    def parent_taxon_qid(self, entity: dict[str, Any]) -> str | None:
        value = _first_snak_value(entity.get("claims", {}), PARENT_TAXON_PROPERTY)
        return value.get("id") if isinstance(value, dict) else None

    def publication_year(self, entity: dict[str, Any]) -> str | None:
        """Extrait l'année depuis la valeur `time` de P574 (format `+1980-00-00T00:00:00Z`) —
        seule la précision année nous intéresse ici, peu importe la précision réelle du point
        Wikidata (jour/mois/année)."""
        value = _first_snak_value(entity.get("claims", {}), PUBLICATION_YEAR_PROPERTY)
        if not isinstance(value, dict) or "time" not in value:
            return None
        time_str = value["time"]
        return time_str[1:5] if len(time_str) >= 5 else None

    async def label_fr(self, qid: str) -> str | None:
        """Résout le label français d'un item référencé par un claim d'une autre entité (ex.
        l'auteur pointé par P405) — `wbgetentities` ne résout jamais les labels des entités
        référencées dans les claims, seulement celles demandées explicitement : un appel séparé
        est incontournable."""
        entity = await self.get_entity(qid)
        if entity is None:
            return None
        return entity.get("labels", {}).get("fr", {}).get("value")
