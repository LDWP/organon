"""Per-article generation options.

One Pydantic model serves as the API request schema, the CLI options
and the web form fields. `taxon` and CLI-only flags are not options.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateOptions(BaseModel):
    """Options controlling the generation of one article."""

    classification: str = Field(
        default="",
        description="La classification à utiliser (vide pour laisser le programme choisir)",
    )
    domain: str = Field(
        default="*",
        description="Le domaine du vivant du taxon, utilisé pour filtrer les sources utilisées",
    )
    gbif_key: int | None = Field(
        default=None,
        description=(
            "Identifiant GBIF déjà résolu (ex. choix dans la liste de désambiguïsation) à "
            "utiliser directement pour la classification GBIF, au lieu de repartir d'une "
            "recherche floue par nom qui peut résoudre vers un enregistrement différent."
        ),
    )

    author_source: str | None = Field(
        default=None,
        description=(
            'Identifiant du module à retenir pour l\'auteur du taxon (ex. "itis"), au lieu du '
            "vote majoritaire entre modules (voir `_majority_author`) — utile quand un module "
            "rapporte une citation d'auteur plus complète que les autres (ex. GBIF/WoRMS tronqués "
            "face à ITIS sur un genre donné). Ignoré si absent des candidats de "
            "`GenerateResponse.author_candidates`."
        ),
    )

    synonym_links: bool = Field(
        default=True, description="Ajouter des wikiliens autour des synonymes"
    )
    infraspecific_links: bool = Field(
        default=False, description="Ajouter des wikiliens pour les taxons inférieurs à l'espèce"
    )
    follow_synonyms: bool = Field(
        default=True,
        description=(
            "Si la classification indique que le taxon demandé est un synonyme, traiter la cible"
        ),
    )
    sort_synonyms: bool = Field(
        default=True,
        description="Trier les synonymes par ordre alphabétique plutôt que l'ordre de la source",
    )
    external_only: bool = Field(
        default=False,
        description="Ne déterminer que les liens externes (les données peuvent être incohérentes)",
    )
    selectors: bool = Field(
        default=True,
        description=(
            "Autorise l'utilisation des règles de définition des ébauches/catégories/portails"
        ),
    )
    plan: bool = Field(
        default=False, description="Générer un plan-type même quand il n'y a pas d'information"
    )
    column_threshold: int = Field(
        default=25, description="Nombre-seuil d'éléments dans une liste avant mise en colonnes"
    )
    list_limit: int = Field(
        default=-1,
        description=(
            "Nombre maximum d'éléments dans les listes (sous-taxons, synonymes) ; "
            "<=0 = pas de limite"
        ),
    )
    timeout: float = Field(
        default=0, description="Durée max de fonctionnement d'un module (0 = pas de timeout)"
    )

    off: list[str] = Field(
        default_factory=list, description="Identifiants des modules à désactiver"
    )

    marine_only: bool = Field(
        default=False,
        description=(
            "Limiter les recherches WoRMS aux taxons marins, plutôt qu'un comportement imposé "
            "silencieusement sans possibilité de le désactiver."
        ),
    )

    homonym_category_key: str = Field(
        default="*",
        description=(
            "Clé de tri de la catégorie homonyme ajoutée pour les taxons de rang embranchement/"
            "classe/ordre/famille (ex. [[Catégorie:Bovidae|*]]) — voir "
            "organon.core.selectors.categorization.compute_footer_links."
        ),
    )
