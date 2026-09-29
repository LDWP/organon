"""Read access to a taxon's Wikidata item, via `wbgetentities`.

Distinct from the WDQS SPARQL service used by
`organon.modules.wikimedia.wikidata.adapter` to resolve a name to a QID:
here the input is already a QID.

`EXTERNAL_ID_PROPERTIES` only covers verified properties, none guessed.
Absent by choice, not oversight: modules whose Wikidata property is
unverified or whose `id` is not Wikidata's (algaebase, eflora,
telametro, reptile_database, wsc, fishbase, taxonomicon, doris, tpdb,
eol).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"

TAXON_NAME_PROPERTY = "P225"
TAXON_RANK_PROPERTY = "P105"

# Rank items (P105); value is a `ranks.yaml` key. An absent rank is not
# guessed: `rank()` returns None.
RANK_QIDS: dict[str, str] = {
    "Q146481": "domaine",
    "Q36732": "règne",
    "Q38348": "phylum",
    "Q37517": "classe",
    "Q36602": "ordre",
    "Q5867959": "sous-ordre",
    "Q2136103": "super-famille",
    "Q35409": "famille",
    "Q164280": "sous-famille",
    "Q227936": "tribu",
    "Q34740": "genre",
    "Q3238261": "sous-genre",
    "Q7432": "espèce",
    "Q68947": "sous-espèce",
    "Q767728": "variété",
    "Q279749": "forme",
    "Q713623": "clade",
}

# GBIF is migrating: P846 (legacy, still the majority) and P14607 (new
# scheme) coexist on Wikidata. Both are kept, P14607 declared after
# P846: when both are present on an item, `external_ids()` must retain
# the newer.
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
    "P12560": "mdd",
    "P4024": "adw",
    "P11043": "hesperomys",
    "P2040": "cites",
    "P685": "ncbi",
    "P3031": "oepp",
    "P5055": "irmng",
    "P3186": "inpn",
    "P627": "iucn",
    "P1745": "vascan",
}


# Database item cited as "stated in" (P248) for each comparable module:
# P9073 of the id property, or P1629 when absent (P14607 has no P9073).
# Q4874420 is the "EPPO code" item, as declared by P9073 of P3031.
DATABASE_ITEMS: dict[str, str] = {
    "gbif": "Q1531570",
    "gbif_col_xr": "Q1531570",
    "itis": "Q82575",
    "wrms": "Q604063",
    "ipni": "Q922063",
    "powo": "Q47542613",
    "indexfungorum": "Q1860469",
    "tropicos": "Q2578548",
    "wfo": "Q77076820",
    "col": "Q38840",
    "mdd": "Q120753297",
    "adw": "Q2850008",
    "hesperomys": "Q113467651",
    "cites": "Q20962955",
    "ncbi": "Q12159796",
    "oepp": "Q4874420",
    "irmng": "Q51885189",
    "inpn": "Q26924544",
    "iucn": "Q32059",
    "vascan": "Q19544711",
}


# Conservation status items (P141). `NE` (not evaluated) is not an
# assessment, hence absent. Key is the code of
# `GenerateResponse.iucn_status`.
IUCN_STATUS_QIDS: dict[str, str] = {
    "LC": "Q211005",
    "NT": "Q719675",
    "VU": "Q278113",
    "EN": "Q96377276",
    "CR": "Q219127",
    "EW": "Q239509",
    "EX": "Q237350",
    "DD": "Q3245245",
}

_BATCH_SIZE = 50
"""Plafond de `wbgetentities` pour `ids` (utilisateur non-bot)."""


@dataclass(frozen=True)
class Statement:
    """A Wikidata statement reduced to what the diagnosis compares.

    Main snak value, rank (`preferred` or `normal`), qualifiers and
    references (one dict property to values per reference).
    """

    value: Any
    rank: str
    qualifiers: dict[str, list[Any]] = field(default_factory=dict)
    references: list[dict[str, list[Any]]] = field(default_factory=list)


def _snak_values(snaks: list[dict[str, Any]]) -> list[Any]:
    """Return the values of the snaks that carry one."""
    return [s["datavalue"]["value"] for s in snaks if "datavalue" in s]


def _first_snak_value(claims: dict[str, Any], prop: str) -> Any | None:
    """Return the main value of the first statement of `prop`."""
    statements = claims.get(prop)
    if not statements:
        return None
    try:
        return statements[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None


class WikidataEntityAdapter(OwnedClientMixin):
    """Read client of Wikidata items."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def get_entity(self, qid: str) -> dict[str, Any] | None:
        """Return an item's claims, French label and frwiki sitelink.

        None if the QID does not exist.
        """
        resp = await self._client.get(
            WIKIDATA_API_URL,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|labels|sitelinks",
                "sitefilter": "frwiki",
                "languages": "fr",
                "format": "json",
            },
        )
        resp.raise_for_status()
        entity = resp.json().get("entities", {}).get(qid)
        if entity is None or "missing" in entity:
            return None
        return entity

    async def get_entities(self, qids: list[str]) -> dict[str, dict[str, Any]]:
        """Return claims and labels of several items, in batches of 50.

        Nonexistent QIDs are absent from the result.
        """
        entities: dict[str, dict[str, Any]] = {}
        for start in range(0, len(qids), _BATCH_SIZE):
            resp = await self._client.get(
                WIKIDATA_API_URL,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(qids[start : start + _BATCH_SIZE]),
                    "props": "claims|labels|sitelinks",
                    "sitefilter": "frwiki",
                    "languages": "fr",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            for qid, entity in resp.json().get("entities", {}).items():
                if "missing" not in entity:
                    entities[qid] = entity
        return entities

    def statements(self, entity: dict[str, Any], prop: str) -> list[Statement]:
        """Return the statements of `prop` that carry a value.

        *deprecated* ones are skipped (Wikidata reserves that rank for
        values not to use), as are `novalue` and `somevalue`.
        """
        result: list[Statement] = []
        for raw in entity.get("claims", {}).get(prop, []):
            rank = raw.get("rank", "normal")
            mainsnak = raw.get("mainsnak", {})
            if rank == "deprecated" or "datavalue" not in mainsnak:
                continue
            result.append(
                Statement(
                    value=mainsnak["datavalue"]["value"],
                    rank=rank,
                    qualifiers={
                        q: _snak_values(snaks) for q, snaks in raw.get("qualifiers", {}).items()
                    },
                    references=[
                        {p: _snak_values(snaks) for p, snaks in ref.get("snaks", {}).items()}
                        for ref in raw.get("references", [])
                    ],
                )
            )
        return result

    def frwiki_title(self, entity: dict[str, Any]) -> str | None:
        """Return the frwiki sitelink title, or None."""
        title = entity.get("sitelinks", {}).get("frwiki", {}).get("title")
        return title if isinstance(title, str) else None

    def taxon_name(self, entity: dict[str, Any]) -> str | None:
        """Return the taxon name (P225), or None."""
        value = _first_snak_value(entity.get("claims", {}), TAXON_NAME_PROPERTY)
        return value if isinstance(value, str) else None

    def external_ids(self, entity: dict[str, Any]) -> dict[str, str]:
        """Return one external id per module."""
        claims = entity.get("claims", {})
        ids: dict[str, str] = {}
        for prop, module_id in EXTERNAL_ID_PROPERTIES.items():
            value = _first_snak_value(claims, prop)
            if isinstance(value, str):
                ids[module_id] = value
        return ids

    def external_id_values(self, entity: dict[str, Any]) -> dict[str, list[str]]:
        """Return all non-deprecated values of each id, per module.

        An item may hold several ids of one database; `external_ids`
        keeps one.
        """
        values: dict[str, list[str]] = {}
        for prop, module_id in EXTERNAL_ID_PROPERTIES.items():
            for statement in self.statements(entity, prop):
                if isinstance(statement.value, str) and statement.value not in values.get(
                    module_id, []
                ):
                    values.setdefault(module_id, []).append(statement.value)
        return values

    def rank(self, entity: dict[str, Any]) -> str | None:
        """Return the taxon rank (P105) as a ranks.yaml key, or None."""
        value = _first_snak_value(entity.get("claims", {}), TAXON_RANK_PROPERTY)
        return RANK_QIDS.get(value["id"]) if isinstance(value, dict) else None
