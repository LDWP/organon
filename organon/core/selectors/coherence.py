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

import re
from collections import Counter

from organon.core.domains import build_module_domain_tree, rec_strict_domaine
from organon.core.models import RegneIncoherence, Struct
from organon.core.registry import get_module

_REGNE_INCONNU = "neutre"
"""Valeur sentinelle utilisée par les tables kingdom->règne (GBIF/ITIS/WoRMS) quand le libellé
de règne renvoyé par la source n'est reconnu dans aucune charte — pas un vrai signal de règne,
donc exclue pour éviter un faux positif à chaque libellé non mappé."""

_YEAR_TOKEN_RE = re.compile(r"\b(1[3-9]\d\d|20\d\d)\b")
"""Mêmes bornes que `organon.core.rendering.authors._YEAR_RE` (1300-2099), mais en recherche
libre (`search`/`findall`) plutôt qu'en correspondance stricte d'un token déjà découpé : sert ici
à repérer une année dans une chaîne d'auteur complète plutôt que dans un seul token isolé."""


def gbif_annee_probable_validee(struct: Struct, auteur_retenu: str | None) -> int | None:
    """Confirme un candidat d'année GBIF (`struct.liens['gbif']['annee_probable']`, extrait par
    regex d'une citation bibliographique en texte libre — GBIF n'expose aucun champ année
    structuré comme POWO/IPNI/Index Fungorum, voir `organon.modules.gbif.module._annee_probable`)
    — non fiable isolément (parsing de texte libre, sans champ dédié), mais utilisable une fois
    recoupée : ne renvoie l'année que si un AUTRE module rapporte la même dans son propre auteur
    (`struct.liens[<module>]['auteur']`). `auteur_retenu` est l'auteur déjà choisi par le vote
    majoritaire (`generate.py::_auteur_majoritaire`) : si celui-ci porte déjà une année, rien à
    ajouter — évite un doublon (ex. "L., 1753, 1753")."""
    if auteur_retenu and _YEAR_TOKEN_RE.search(auteur_retenu):
        return None
    annee = struct.liens.get("gbif", {}).get("annee_probable")
    if annee is None:
        return None
    cible = str(annee)
    for module_id, data in struct.liens.items():
        if module_id == "gbif" or not isinstance(data, dict):
            continue
        if cible in _YEAR_TOKEN_RE.findall(data.get("auteur") or ""):
            return annee
    return None


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


def classification_regne_coherents(
    successes: list[str], regnes: dict[str, str]
) -> tuple[list[str], list[str], str | None]:
    """Sépare les modules de classification ayant réussi entre ceux dont le règne rejoint la
    majorité et ceux qui s'en écartent — un homonyme inter-règnes (ex. "Morus" : mûrier chez les
    botanistes, fou de Bassan chez les zoologistes, voir le module-docstring) ne doit pas
    l'emporter sur `meilleure_classification` au seul motif d'une spécialisation ou priorité de
    module plus élevée que la majorité des autres sources. Retourne aussi ce règne majoritaire
    (ou None si aucune majorité fiable) : `_pick_classification_winner` s'en sert pour arbitrer
    par spécialisation même sans filtre explicite (`domaine == "*"`).

    Ne tranche que sur une VRAIE majorité (règne présent dans plus de la moitié des candidats
    au règne connu) : à égalité ou en dessous, la situation est ambiguë (pas assez de signal
    pour désigner un outlier) et aucun candidat n'est exclu. Règne vide/"neutre" : aucun signal
    fiable, candidat toujours conservé quel que soit le résultat de la majorité."""
    signalles = {cid: regnes[cid] for cid in successes if regnes.get(cid) and regnes[cid] != _REGNE_INCONNU}
    if len(signalles) < 2:
        return successes, [], None

    regne_majoritaire, effectif_majoritaire = Counter(signalles.values()).most_common(1)[0]
    if effectif_majoritaire * 2 <= len(signalles):
        return successes, [], None

    exclus = [cid for cid in successes if signalles.get(cid, regne_majoritaire) != regne_majoritaire]
    coherents = [cid for cid in successes if cid not in exclus]
    return coherents, exclus, regne_majoritaire


def reference_module_coherente(module_id: str, regne: str) -> bool:
    """Un module de référence taxonomique est-il cohérent avec le règne retenu pour ce taxon ?
    S'appuie sur `ModuleMeta.domains` (déjà utilisé pour sélectionner les classifications
    possibles, voir `organon.core.domains`) plutôt que sur une liste ad hoc : un module dont le
    domaine déclaré exclut le règne du taxon (ex. IndexFungorum, réservé aux champignons,
    référencé sur un animal) est jugé incohérent. Règne vide ou "neutre" (rang au-dessus de
    l'espèce, ou règne non résolu) : aucune détection fiable possible, jugé cohérent par défaut
    plutôt que de décocher à tort."""
    if not regne or regne == _REGNE_INCONNU:
        return True
    module = get_module(module_id)
    if module is None:
        return True
    return rec_strict_domaine(regne, build_module_domain_tree(module.meta.domains))
