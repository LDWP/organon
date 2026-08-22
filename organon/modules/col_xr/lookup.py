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


async def find_col_xr_id(adapter: ColXrAdapter, nom: str, domaine: str) -> str | None:
    """None si aucune entrée COL XR acceptée ne correspond au nom (et au règne, si `domaine` est
    renseigné) — un simple défaut d'absence, pas une erreur : GBIF garde alors son identifiant
    numérique habituel. Ignore délibérément les synonymes (contrairement à `ColXrModule`) : un
    lien de référence doit pointer vers la même fiche acceptée que celle déjà résolue par GBIF,
    jamais vers un statut différent."""
    results = await adapter.search(nom)
    if not results:
        return None

    # Même filtre client strict que `ColXrModule` : `type=EXACT` côté ChecklistBank ne suffit
    # pas à exclure tous les à-peu-près.
    exact = [r for r in results if r["usage"]["name"]["scientificName"] == nom]
    candidats = exact or results

    def _regne_correspond(r: dict) -> bool:
        if domaine in ("*", ""):
            return True
        idx = _kingdom_index(r.get("classification", []))
        kingdom = r["classification"][idx]["name"] if idx is not None else ""
        return KINGDOM_MAP.get(kingdom, "") == domaine

    accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
    cur = next((r for r in accepted if _regne_correspond(r)), None)
    if cur is None:
        cur = accepted[0] if accepted else None
    if cur is None:
        return None
    return cur["id"]
