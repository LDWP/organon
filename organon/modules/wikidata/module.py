"""Vérification croisée entre les identifiants externes déjà résolus par organon
(`struct.liens[<id-module>]["id"]`) et ceux portés par l'item Wikidata du taxon — jamais
d'écriture ici, uniquement un diagnostic d'écarts à faire valider par l'utilisateur avant toute
correction poussée manuellement (voir `AuthSettings.wikidata_edit_enabled`, désactivé et non
implémenté tant que le mode de conservation du jeton OAuth et l'enregistrement du consumer
d'édition Wikibase ne sont pas tranchés).

Volontairement non enregistré via `@register_module` : ce module n'intervient pas dans le
pipeline de génération (`TaxonomyModule.collect`), seulement en amont (résolution d'un QID en
recherche, voir `organon.api.routes.search`) et en aval (ce diff, post-génération).

Le rapprochement auteur/année (P405/P574) n'est volontairement pas couvert ici : `struct.taxon
.auteur` combine nom et année dans une seule chaîne déjà mise en forme (voir `format_auteur`),
alors que Wikidata les porte en deux claims séparés — une comparaison fiable demande de décider
d'abord quelle normalisation appliquer des deux côtés, pas encore tranché."""

from __future__ import annotations

from dataclasses import dataclass

from organon.core.models import Struct
from organon.modules.wikidata.adapter import WikidataAdapter


@dataclass
class WikidataDiscrepancy:
    module_id: str
    organon_value: str
    wikidata_value: str


def diff_external_ids(
    struct: Struct, entity: dict, adapter: WikidataAdapter
) -> list[WikidataDiscrepancy]:
    """Ne signale que les désaccords francs (identifiant présent des deux côtés mais différent),
    jamais une simple absence côté Wikidata (Wikidata n'a pas vocation à tout référencer) ni côté
    organon (un module peut ne pas avoir trouvé le taxon sans que ce soit une erreur)."""
    discrepancies = []
    for module_id, wikidata_value in adapter.external_ids(entity).items():
        lien = struct.liens.get(module_id)
        if not lien or "id" not in lien:
            continue
        organon_value = str(lien["id"])
        if organon_value != wikidata_value:
            discrepancies.append(
                WikidataDiscrepancy(
                    module_id=module_id, organon_value=organon_value, wikidata_value=wikidata_value
                )
            )
    return discrepancies
