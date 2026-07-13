"""Orchestrateur de rendu : assemble les sections de l'article dans l'ordre attendu."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.rendering import sections


def _compute_ebauche(struct: Struct, options: GenerateOptions) -> list[str]:
    """Tente d'abord les règles (categories/ebauches/portails, voir organon.core.selectors),
    puis retombe sur la table par règne. Import différé pour éviter un cycle (selectors ->
    models, jamais rendering -> selectors au niveau module)."""
    from organon.core.selectors.categorization import wp_ebauche

    return wp_ebauche(struct, options)


def render_taxobox_block(struct: Struct, options: GenerateOptions) -> str:
    """Rendu isolé du bloc `{{ébauche}}` → `{{Taxobox fin}}`, réutilisé par `render()` et par
    l'API pour permettre d'échanger ce bloc seul (changer de source de classification) sans
    regénérer tout l'article."""
    ebauche = _compute_ebauche(struct, options)
    return sections.render_taxobox(struct, options, ebauche)


def render_subtaxa_block(struct: Struct, options: GenerateOptions) -> str:
    """Rendu isolé de la section "Liste des taxons de rang inférieur", réutilisé par `render()`
    et par l'API selon le même principe que `render_taxobox_block` : permet d'échanger cette
    section seule (changer de source pour les sous-taxons) sans regénérer tout l'article."""
    return sections.render_inf(struct, options)


def render(struct: Struct, options: GenerateOptions, ext_only: bool = False) -> str:
    """Assemble l'article complet. `ext_only=True` ne génère que la zone "Voir aussi" / liens
    externes, sans le reste de l'article."""
    ret = ""

    if not ext_only:
        ret += render_taxobox_block(struct, options)
        ret += sections.render_intro(struct)
        ret += sections.render_description(struct, options)
        ret += sections.render_distribution(struct, options)
        ret += render_subtaxa_block(struct, options)
        ret += sections.render_supp(struct, options)
        ret += sections.render_etymologie(struct, options)
        ret += sections.render_originale(struct, options)

    ret += sections.render_voir_aussi(struct, options)

    if not ext_only:
        ret += sections.render_fin(struct)

    while "\n\n\n" in ret:
        ret = ret.replace("\n\n\n", "\n\n")

    return ret
