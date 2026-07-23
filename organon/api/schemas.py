"""Schémas de requête/réponse de l'API JSON. `GenerateRequest` hérite de `GenerateOptions`
(organon.core.config) : un seul modèle sert à la fois de schéma de requête API, de base des
flags CLI et de champs de formulaire web."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from organon.core.config import GenerateOptions
from organon.core.db_inventory import DbInventory
from organon.core.models import RegneIncoherence


class GenerateRequest(GenerateOptions):
    taxon: str = Field(..., description="Le nom scientifique du taxon à traiter")


class ExternalLink(BaseModel):
    """Un lien externe de debug (`TaxonomyModule.debug_link`), attribué à son module d'origine —
    nécessaire côté frontend pour l'associer à la bonne ligne du tableau de suivi par module
    (onglet Données), plutôt qu'une simple liste de HTML sans moyen de savoir quel module a
    produit quel lien."""

    module_id: str
    html: str


class RankLine(BaseModel):
    """Un rang de la taxobox (voir `organon.core.rendering.sections.compute_rank_lines`), avec
    sa ligne wikitexte déjà mise en forme — exposé structuré pour permettre de comparer les
    rangs entre plusieurs classifications d'un même taxon (désaccord de source à un rang donné,
    voir `{{Taxobox conflit}}`) sans reconstruire la ligne côté frontend."""

    rang: str
    nom: str
    line: str


class GenerateResponse(BaseModel):
    taxon_requested: str
    taxon_resolved: str
    classification_used: str
    domain_used: str
    regne: str = ""
    eteint: bool = False
    vernacular_names: list[str] = []
    wikitext: str
    taxobox_wikitext: str
    """Le bloc `{{ébauche}}` → `{{Taxobox fin}}` isolé du reste de `wikitext` — permet de
    changer de source de classification en ne remplaçant que ce bloc dans l'article d'une
    autre source, sans regénérer les autres sections (systématique, publication originale,
    liens externes...)."""
    subtaxa_wikitext: str = ""
    """La section "Liste des taxons de rang inférieur" isolée du reste de `wikitext`, selon le
    même principe que `taxobox_wikitext` — permet de choisir indépendamment la source qui
    alimente la taxobox et celle qui alimente les sous-taxons plutôt qu'un bloc unique."""
    taxobox_completeness_score: int = 0
    """Mesure de complétude de la taxobox de cette classification (nombre de rangs trouvés) —
    sert à recommander automatiquement une source pour la facette "taxobox" du zoom
    classification, indépendamment de la facette "taxons inférieurs" (voir
    `subtaxa_completeness_score`). Les deux facettes étaient auparavant agrégées dans un unique
    `completeness_score` ; elles sont séparées ici car l'utilisateur peut vouloir retenir une
    source pour la taxobox et une autre pour les sous-taxons."""
    subtaxa_completeness_score: int = 0
    """Mesure de complétude des sous-taxons de cette classification (nombre de taxons de rang
    inférieur trouvés) — pendant de `taxobox_completeness_score` pour la facette "taxons
    inférieurs". Les synonymes et noms vernaculaires ne sont volontairement rattachés à aucune
    des deux facettes : ils ne font partie ni du bloc taxobox ni du bloc sous-taxons
    (`taxobox_wikitext`/`subtaxa_wikitext`), donc les compter dans l'un ou l'autre score
    fausserait le classement sans bénéfice pour le choix que ces scores éclairent."""
    rank_lines: list[RankLine] = []
    external_links: list[ExternalLink] = []
    data_found: dict[str, list[str]] = {}
    """Pour chaque module ayant contribué à cette génération, la liste des catégories
    d'information qu'il a effectivement rapportées (ex. "Classification", "Taxons inférieurs",
    "Auteur"...) — dérivée des champs déjà peuplés du `Struct` (quel module est la source des
    sous-taxons/synonymes, quelles clés de noms vernaculaires/répartition sont non vides...)
    plutôt que maintenue à la main module par module. Alimente la colonne "Informations" de
    l'onglet Données côté frontend."""
    auteur_candidats: dict[str, str] = {}
    """Pour chaque module ayant rapporté un auteur pour ce taxon, l'auteur brut qu'il rapporte —
    avant vote majoritaire entre modules (voir `_auteur_majoritaire`). Permet à l'utilisateur
    d'imposer une source via `GenerateOptions.auteur_source` plutôt que de subir le vote
    automatique (ex. Campylobacter : ITIS rapporte une citation d'auteur plus complète que
    GBIF/WoRMS)."""
    logs: list[str] = []
    warnings: list[str] = []
    elapsed_seconds: float
    truncated: dict[str, bool] = {}
    regne_incoherences: list[RegneIncoherence] = []
    """Modules d'enrichissement dont le règne détecté diffère de celui retenu par la
    classification — signe possible d'homonymie inter-règnes (voir RegneIncoherence).
    Détection partielle : seuls quelques modules (GBIF/ITIS/WoRMS) exposent ce signal sans coût
    réseau supplémentaire ; son absence ne garantit donc pas la cohérence."""


class ModuleStatusEvent(BaseModel):
    """Un événement SSE de `POST /api/v1/generate/stream` : progression d'un module de
    classification ou d'enrichissement pendant une génération en cours. `status="running"` est
    émis juste avant l'appel réseau du module, puis exactement un des trois statuts terminaux
    ("found"/"empty"/"error") une fois l'appel terminé — jamais les deux à la fois pour un même
    module dans une même génération."""

    type: Literal["module_status"] = "module_status"
    module_id: str
    role: Literal["classification", "enrichment"]
    status: Literal["running", "found", "empty", "error"]
    message: str | None = None
    """Détail de l'erreur, uniquement quand status == "error"."""


class PlanEvent(BaseModel):
    """Émis une seule fois, juste après le succès de la classification : liste les modules
    d'enrichissement qui vont être exécutés, pour que le frontend puisse afficher toutes les
    lignes de statut (en attente) avant même que le premier module ne démarre."""

    type: Literal["plan"] = "plan"
    classification_id: str
    modules: list[str]


class ResultEvent(BaseModel):
    """Dernier événement d'une génération réussie : porte la même donnée que la réponse de
    `POST /api/v1/generate` (`GenerateResponse`), pour que le frontend n'ait pas à la
    reconstituer lui-même à partir des événements de progression."""

    type: Literal["result"] = "result"
    data: GenerateResponse


class FatalErrorEvent(BaseModel):
    """Émis quand la génération ne peut pas aboutir (ex. taxon non trouvé via le module de
    classification, ou erreur réseau sur ce module) — équivalent en SSE d'une `HTTPException`,
    utilisé ici parce que le code de statut HTTP de la réponse (200) est déjà figé au moment où
    cet événement est produit (les en-têtes SSE sont envoyés dès le premier octet)."""

    type: Literal["fatal_error"] = "fatal_error"
    status_code: int
    detail: str


class SearchMatch(BaseModel):
    """`gbif_key`/`parent_key` viennent tels quels de `key`/`parentKey` (GBIF) : permettent au
    frontend de reconstruire une filiation *confirmée* entre deux suggestions de la même
    réponse (ex. une sous-espèce dont le `parent_key` pointe vers le `gbif_key` d'une espèce
    listée juste au-dessus), plutôt qu'une simple ressemblance textuelle de noms."""

    scientific_name: str
    author: str = ""
    extinct: bool = False
    kingdom: str = ""
    rank: str = ""
    vernacular_names: list[str] = []
    source: str = "GBIF"
    gbif_key: int | None = None
    parent_key: int | None = None


class SearchResponse(BaseModel):
    query: str
    matches: list[SearchMatch] = []


class ModuleInfo(BaseModel):
    id: str
    can_classify: bool
    can_render_external_link: bool
    domains: str | list[str]
    priority: int
    is_default: bool


class DomainInfo(BaseModel):
    id: str
    parent: str | None = None


class VersionInfo(BaseModel):
    version: str


class SourcesResponse(DbInventory):
    """Réponse de GET /api/v1/sources. Alias de DbInventory (organon.core.db_inventory) : la
    forme de la réponse API est exactement celle du fichier de données fusionné avec le
    registre de modules, pas besoin d'une enveloppe séparée."""


class CommonsImageSuggestion(BaseModel):
    """Une image Commons proposée pour la taxobox (voir
    `organon.modules.commons_images.service.find_images`) : déjà filtrée par licence et par
    distinction qualité/featured, jamais une simple recherche brute."""

    file_name: str
    thumb_url: str
    page_url: str
    license_code: str
    license_label: str
    assessments: list[str] = []
    is_wikidata_image: bool = False
    """True si cette même image est déjà utilisée par l'item Wikidata du taxon (P18) — la
    proposer resterait correct mais ne serait pas une nouveauté, voir la spec du frontend."""


class CommonsImagesResponse(BaseModel):
    taxon: str
    category_title: str
    search_url: str
    category_url: str | None = None
    suggestions: list[CommonsImageSuggestion] = []


class TaxoboxRefreshRequest(BaseModel):
    page_title: str = Field(..., description="Titre de la page Wikipédia à éditer")
    wikitext: str = Field(
        ..., description="Wikitexte complet à écrire sur la page (ex. produit par /api/v1/generate)"
    )


class TaxoboxRefreshResponse(BaseModel):
    page_title: str
    new_revision_id: int
    requested_by: str
