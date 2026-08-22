"""Résolution allégée de l'identifiant ChecklistBank (Catalogue of Life Extended Release,
dataset 3LXR) correspondant à un nom déjà résolu par ailleurs — utilisée uniquement par
`organon/modules/gbif/module.py` pour son propre lien {{GBIF}} (accepté par Modèle:GBIF réformé,
voir gbif.org/taxon/{id}) et un second lien {{CatalogueofLife}}. Distincte de
`organon.modules.col_xr.module.ColXrModule`, la classification COL XR à part entière
(`can_classify=True`) : les deux référentiels peuvent diverger (voir sa docstring), ce lookup ne
sert que d'identifiant d'affichage pour la classification déjà retenue par GBIF, jamais à piloter
une classification.

Ne fait aucun appel HTTP directement, voir adapter.py."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP
from organon.modules.col_xr.adapter import ColXrAdapter


def _kingdom_index(classification: list[dict]) -> int | None:
    return next((i for i, c in enumerate(classification) if c.get("rank") == "kingdom"), None)


def _regne_correspond(r: dict, domaine: str) -> bool:
    if domaine in ("*", ""):
        return True
    idx = _kingdom_index(r.get("classification", []))
    kingdom = r["classification"][idx]["name"] if idx is not None else ""
    return KINGDOM_MAP.get(kingdom, "") == domaine


def _exact_matches(results: list[dict], nom: str) -> list[dict]:
    # Même filtre client strict que l'ancien module de classification : `type=EXACT` côté
    # ChecklistBank ne suffit pas à exclure tous les à-peu-près.
    exact = [r for r in results if r["usage"]["name"]["scientificName"] == nom]
    return exact or results


def _pick(candidats: list[dict], domaine: str) -> dict | None:
    cur = next((r for r in candidats if _regne_correspond(r, domaine)), None)
    return cur if cur is not None else (candidats[0] if candidats else None)


async def find_col_xr_id(adapter: ColXrAdapter, nom: str, domaine: str) -> str | None:
    """None si aucune entrée COL XR acceptée ne correspond au nom (et au règne, si `domaine` est
    renseigné) — un simple défaut d'absence, pas une erreur : GBIF garde alors son identifiant
    numérique habituel. Ignore délibérément les synonymes (contrairement à `ColXrModule`) : un
    lien de référence doit pointer vers la même fiche acceptée que celle déjà résolue par GBIF,
    jamais vers un statut différent."""
    results = await adapter.search(nom)
    if not results:
        return None
    candidats = _exact_matches(results, nom)
    accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
    cur = _pick(accepted, domaine)
    return cur["id"] if cur is not None else None

async def resolve_col_xr_concept_id(adapter: ColXrAdapter, nom: str, domaine: str) -> str | None:
    """Identifiant ChecklistBank du concept taxonomique ACCEPTÉ désigné par `nom`, que `nom` soit
    lui-même le nom accepté ou un synonyme que COL XR redirige explicitement vers lui
    (`usage.accepted.id`) — contrairement à `find_col_xr_id`, qui ignore les synonymes pour ne
    jamais faire pointer un lien externe vers un statut différent du sien. Utilisé par
    `organon.core.rendering.subtaxa_merge.reconcile_synonym_groups` pour reconnaître comme un seul
    taxon deux noms orthographiés différemment par deux sources (ex. Discussion Projet:Biologie/
    Organon #30) quand COL XR les relie explicitement — jamais par ressemblance de nom seule.
    None si `nom` n'a aucune entrée COL XR (accepté ou synonyme redirigé) correspondante."""
    results = await adapter.search(nom)
    if not results:
        return None
    candidats = _exact_matches(results, nom)

    accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
    cur = _pick(accepted, domaine)
    if cur is not None:
        return cur["id"]

    synonymes = [
        r for r in candidats if r["usage"]["status"] == "synonym" and r["usage"].get("accepted")
    ]
    cur = _pick(synonymes, domaine)
    return cur["usage"]["accepted"]["id"] if cur is not None else None
