"""Options de génération d'un article.

Un seul modèle Pydantic sert de schéma de requête API (`organon.api.schemas`), de base pour
les options de la CLI (`organon.cli.main`) et de champs du formulaire web — une seule liste
à maintenir plutôt que trois copies séparées.

`taxon` n'est volontairement pas ici : c'est un paramètre à part de la requête de génération
(voir `GenerateRequest` dans `organon.api.schemas`), pas une "option". De même, `debug`,
`debugc`, `liste`, `help`, `version` ne sont pas des options de génération : ce sont des
préoccupations CLI/endpoints séparées (les logs sont toujours renvoyés dans la réponse,
`--list-modules`/`GET /api/v1/modules` liste les modules, etc.).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AuteursMode = Literal["s", "n", "n1"]


class GenerateOptions(BaseModel):
    classification: str = Field(
        default="",
        description="La classification à utiliser (vide pour laisser le programme choisir)",
    )
    domaine: str = Field(
        default="*",
        description="Le domaine du vivant du taxon, utilisé pour filtrer les sources utilisées",
    )
    force_regne: str = Field(
        default="",
        description="Force le règne (charte). Utile uniquement avec 'juste_ext'.",
    )
    force_rang: str = Field(
        default="",
        description="Force le rang. Utile uniquement avec 'juste_ext'.",
    )
    gbif_key: int | None = Field(
        default=None,
        description=(
            "Identifiant GBIF déjà résolu (ex. choix dans la liste de désambiguïsation) à "
            "utiliser directement pour la classification GBIF, au lieu de repartir d'une "
            "recherche floue par nom qui peut résoudre vers un enregistrement différent."
        ),
    )

    auteurs: AuteursMode = Field(
        default="n",
        description="Mode de traitement des auteurs : s=standard, n=nouveau, n1=nouveau+ajout réponse unique",
    )

    liens_synonymes: bool = Field(default=True, description="Ajouter des wikiliens autour des synonymes")
    liens_inf_sp: bool = Field(
        default=False, description="Ajouter des wikiliens pour les taxons inférieurs à l'espèce"
    )
    suivre_synonymes: bool = Field(
        default=True,
        description="Si la classification indique que le taxon demandé est un synonyme, traiter la cible",
    )
    trier_synonymes: bool = Field(
        default=True, description="Trier les synonymes par ordre alphabétique plutôt que l'ordre de la source"
    )
    inclure_invalides: bool = Field(
        default=False, description="Inclure dans les liens externes les taxons invalides trouvés"
    )
    juste_ext: bool = Field(
        default=False,
        description="Ne déterminer que les liens externes (les données peuvent être incohérentes)",
    )
    selecteurs: bool = Field(
        default=True,
        description="Autorise l'utilisation des règles de définition des ébauches/catégories/portails",
    )
    plan: bool = Field(
        default=False, description="Générer un plan-type même quand il n'y a pas d'information"
    )
    article: bool = Field(default=False, description="Ne générer que le texte de l'article, rien d'autre")

    seuil_colonnes: int = Field(
        default=25, description="Nombre-seuil d'éléments dans une liste avant mise en colonnes"
    )
    limite_listes: int = Field(
        default=-1, description="Nombre maximum d'éléments dans les listes (sous-taxons, synonymes) ; <=0 = pas de limite"
    )
    timeout: float = Field(default=0, description="Durée max de fonctionnement d'un module (0 = pas de timeout)")

    off: list[str] = Field(default_factory=list, description="Identifiants des modules à désactiver")
    ua: str = Field(default="", description="User-Agent personnalisé pour les requêtes HTTP")

    marine_only: bool = Field(
        default=False,
        description=(
            "Limiter les recherches WoRMS aux taxons marins, plutôt qu'un comportement imposé "
            "silencieusement sans possibilité de le désactiver."
        ),
    )
