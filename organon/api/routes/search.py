"""GET /api/v1/search — recherche floue par nom scientifique ou vernaculaire, avant génération.

S'appuie sur `GbifAdapter.search_any` (endpoint `species/search`, distinct de l'endpoint de
résolution exacte utilisé par le module GBIF) : matche aussi bien "Gadus morhua" que "morue
franche", et résout au passage l'homonymie entre règnes (ex. "Morus" = mûrier chez les
végétaux, fou de Bassan chez les animaux) puisque `species/search` renvoie un résultat distinct
par règne pour un même nom. Dédupliqué par (nom scientifique, règne) : GBIF renvoie parfois
plusieurs enregistrements pour la même combinaison (variantes d'auteur, sources multiples au
sein du Backbone).

Chaque `SearchMatch` porte aussi `gbif_key`/`parent_key` (tels quels de `key`/`parentKey` côté
GBIF) : le frontend peut ainsi confirmer qu'une suggestion est réellement la sous-espèce d'une
autre suggestion de la même réponse (`parent_key` pointant vers le `gbif_key` d'une entrée
listée), plutôt que de se fier à une ressemblance textuelle des noms qui mélangerait à tort des
taxons sans rapport partageant un même préfixe (ex. un virus nommé d'après son hôte)."""

from __future__ import annotations

import re

from fastapi import APIRouter

from organon.api.schemas import SearchMatch, SearchResponse
from organon.core.domains import KINGDOM_MAP
from organon.core.rendering.grammar import wp_nom_rang
from organon.modules.gbif.adapter import GbifAdapter
from organon.modules.gbif.ranks import gbif_cherche_rang
from organon.modules.wikidata.adapter import WikidataAdapter

router = APIRouter()

MAX_MATCHES = 8
MAX_VERNACULAR_PER_MATCH = 5

_QID_RE = re.compile(r"^Q[1-9]\d*$", re.IGNORECASE)


def _preferred_vernaculars(raw: list[dict]) -> list[str]:
    francais = [v["vernacularName"] for v in raw if v.get("language") == "fra"]
    autres = [v["vernacularName"] for v in raw if v.get("language") != "fra"]
    vus: dict[str, None] = {}
    for nom in francais + autres:
        vus.setdefault(nom, None)
    return list(vus)[:MAX_VERNACULAR_PER_MATCH]


def _relevance(match: SearchMatch, query: str) -> int:
    """Une correspondance exacte (nom scientifique, puis nom vernaculaire) doit apparaître en
    tête plutôt que dans l'ordre brut de `species/search`, qui mélange homonymes et variantes
    (sous-espèces, formes) sans toujours placer le nom demandé en premier."""
    query_lower = query.lower()
    if match.scientific_name.lower() == query_lower:
        return 0
    if any(v.lower() == query_lower for v in match.vernacular_names):
        return 1
    return 2


def _rank_label(rank_raw: str) -> str:
    """Traduit le rang GBIF (ex. "GENUS") vers le libellé français utilisé partout ailleurs
    dans l'app (table `organon/core/data/ranks.yaml`), plutôt qu'un second vocabulaire de
    rangs propre à la recherche."""
    rang_id = gbif_cherche_rang(rank_raw)
    if rang_id == "NOTFOUND":
        return rank_raw.lower()
    label = wp_nom_rang(rang_id, False, False, False)
    return label if label != "NOTFOUND" else rank_raw.lower()


@router.get("/search", response_model=SearchResponse)
async def search(q: str) -> SearchResponse:
    query = q.strip()
    if not query:
        return SearchResponse(query=q, matches=[])

    if _QID_RE.match(query):
        return await _search_by_qid(query.upper())

    adapter = GbifAdapter()
    try:
        raw_results = await adapter.search_any(query, limit=30)
    finally:
        await adapter.aclose()

    # Dédoublonné par identifiant GBIF (`key`), pas par (nom, règne) : plusieurs taxons
    # authentiquement distincts peuvent partager le même nom **et** le même règne (ex.
    # "Acanthocephala" désigne à la fois un phylum de vers et un genre d'insectes, tous deux
    # Animalia — dédupliquer sur (nom, règne) les aurait silencieusement fusionnés en un seul
    # résultat, masquant l'homonymie qu'on cherche justement à révéler).
    seen: dict[int | str, SearchMatch] = {}
    for entry in raw_results:
        nom = entry.get("canonicalName") or entry.get("scientificName")
        if not nom:
            continue
        kingdom_raw = entry.get("kingdom", "")
        dedup_key = entry.get("key") or (nom, kingdom_raw, entry.get("authorship", ""))
        if dedup_key in seen:
            continue
        seen[dedup_key] = SearchMatch(
            scientific_name=nom,
            author=entry.get("authorship", "").strip(),
            extinct=bool(entry.get("extinct", False)),
            kingdom=KINGDOM_MAP.get(kingdom_raw, kingdom_raw.lower()),
            rank=_rank_label(entry.get("rank", "")),
            vernacular_names=_preferred_vernaculars(entry.get("vernacularNames", [])),
            gbif_key=entry.get("key"),
            parent_key=entry.get("parentKey"),
        )

    # Dédoublonné sur l'ensemble des résultats bruts avant de trier par pertinence puis de
    # couper à MAX_MATCHES — trier avant de couper, pas l'inverse, sinon la correspondance
    # exacte pourrait être perdue si elle arrive après la position MAX_MATCHES côté GBIF.
    matches = sorted(seen.values(), key=lambda m: _relevance(m, query))[:MAX_MATCHES]
    return SearchResponse(query=q, matches=matches)


async def _search_by_qid(qid: str) -> SearchResponse:
    """Résout un QID Wikidata en un `SearchMatch` unique porteur des identifiants externes déjà
    connus par l'item (voir `WikidataAdapter.external_ids`) — pas de logique de pertinence ni de
    dédoublonnage, un QID désigne un item précis, pas une requête floue."""
    adapter = WikidataAdapter()
    try:
        entity = await adapter.get_entity(qid)
        if entity is None:
            return SearchResponse(query=qid, matches=[])

        nom = adapter.taxon_name(entity)
        if not nom:
            return SearchResponse(query=qid, matches=[])

        match = SearchMatch(
            scientific_name=nom,
            source="Wikidata",
            qid=qid,
            external_ids=adapter.external_ids(entity),
        )
        return SearchResponse(query=qid, matches=[match])
    finally:
        await adapter.aclose()
