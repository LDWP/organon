"""Calcul de l'ébauche et des portails/catégories, en s'appuyant sur le moteur de règles sûr
de `organon.core.selectors.engine` plutôt que sur `eval()`. Ce calcul n'appelle aucune API
tierce — c'est une simple dérivation à partir de `Struct` déjà résolu — donc il vit ici plutôt
que dans `organon.modules.*` : "fin"/"externe" sont des pseudo-modules internes, pas des
adaptateurs de base tierce."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.rendering.grammar import CATEGORIE_PAR_REGNE, EBAUCHE_PAR_REGNE
from organon.core.selectors.engine import evaluate_ruleset

# Portail par défaut selon le règne.
_PORTAIL_PAR_REGNE: dict[str, str] = {
    "animal": "zoologie",
    "végétal": "botanique",
    "champignon": "mycologie",
    "algue": "phycologie",
    "reptile": "herpétologie",
    "amphibien": "herpétologie",
    "virus": "virologie",
    "archaea": "microbiologie",
    "bactérie": "microbiologie",
    "protiste": "microbiologie",
}
_PORTAIL_DEFAUT = "biologie"


def wp_ebauche(struct: Struct, options: GenerateOptions) -> list[str]:
    """Essaie d'abord les règles (ebauches.yaml/.local.yaml), sinon retombe sur la table par
    règne."""
    if options.selecteurs:
        ret = evaluate_ruleset("ebauches", struct)
        if ret is not None:
            return ret
    if struct.regne in EBAUCHE_PAR_REGNE:
        return [EBAUCHE_PAR_REGNE[struct.regne]]
    return []


def lien_pour_categorie(struct: Struct, options: GenerateOptions) -> list[str] | None:
    if options.selecteurs:
        ret = evaluate_ruleset("categories", struct)
        if ret is not None:
            return ret
    if struct.regne in CATEGORIE_PAR_REGNE and CATEGORIE_PAR_REGNE[struct.regne]:
        return [CATEGORIE_PAR_REGNE[struct.regne]]
    return None


def lien_pour_portail(portail_defaut: str, struct: Struct, options: GenerateOptions) -> list[str] | None:
    if options.selecteurs:
        ret = evaluate_ruleset("portails", struct)
        if ret is not None:
            return ret
    return None


def compute_fin_liens(struct: Struct, options: GenerateOptions) -> dict[str, list[str]]:
    """Calcule le contenu de struct.liens['fin'] (portails + catégories), sans l'assigner
    directement : l'appelant (orchestration de génération, voir
    `organon.api.routes.generate`) est responsable de l'assignation, pour éviter de muter
    `Struct` par effet de bord caché à travers le pipeline."""
    portail_defaut = _PORTAIL_PAR_REGNE.get(struct.regne, _PORTAIL_DEFAUT)
    portails = lien_pour_portail(portail_defaut, struct, options) or [portail_defaut]

    categories = [r.nom for r in struct.rangs if r.rang == "famille"]
    categories.extend(lien_pour_categorie(struct, options) or [])

    return {"portails": portails, "categories": categories}
