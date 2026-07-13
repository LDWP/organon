"""Détection d'incohérence de règne entre le module de classification et un module
d'enrichissement (voir `organon.core.models.RegneIncoherence`) — une même chaîne de
caractères peut désigner des taxons homonymes sans rapport selon la source (ex. "Morus" =
mûrier chez les botanistes vs fou de Bassan chez les zoologistes) ; quand un module
d'enrichissement expose un règne détecté qui diffère de celui retenu par la classification,
c'est un signe possible de cette situation plutôt qu'un simple enrichissement du même taxon.

Ce calcul n'appelle aucune API tierce — comme `categorization.py`, c'est une dérivation pure à
partir de `Struct` déjà résolu — donc il vit ici plutôt que dans `organon.modules.*`.
"""

from __future__ import annotations

from organon.core.models import RegneIncoherence, Struct

_REGNE_INCONNU = "neutre"
"""Valeur sentinelle utilisée par les tables kingdom->règne (GBIF/ITIS/WoRMS) quand le libellé
de règne renvoyé par la source n'est reconnu dans aucune charte — pas un vrai signal de règne,
donc exclue pour éviter un faux positif à chaque libellé non mappé."""


def detect_regne_incoherences(struct: Struct, classification_id: str) -> list[RegneIncoherence]:
    """Parcourt `struct.liens` à la recherche de modules d'enrichissement dont le champ
    `regne_detecte` diffère de `struct.regne`. Détection partielle et honnête : seuls les
    modules qui exposent ce signal sans appel réseau supplémentaire (actuellement GBIF, ITIS,
    WoRMS — voir leurs `module.py`) peuvent déclencher une incohérence ici."""
    incoherences: list[RegneIncoherence] = []
    for module_id, data in struct.liens.items():
        if module_id == classification_id or not isinstance(data, dict):
            continue
        regne_detecte = data.get("regne_detecte")
        if regne_detecte and regne_detecte != _REGNE_INCONNU and regne_detecte != struct.regne:
            incoherences.append(
                RegneIncoherence(module=module_id, regne_suggere=regne_detecte, regne_retenu=struct.regne)
            )
    return incoherences
