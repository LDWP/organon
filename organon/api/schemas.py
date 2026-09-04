"""Schémas de requête/réponse de l'API JSON. `GenerateRequest` hérite de `GenerateOptions`
(organon.core.config) : un seul modèle sert à la fois de schéma de requête API, de base des
flags CLI et de champs de formulaire web."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from organon.core.config import GenerateOptions
from organon.core.db_inventory import DbInventory
from organon.core.models import Basionym, RangIncoherence, RankName, RegneIncoherence


class GenerateRequest(GenerateOptions):
    taxon: str = Field(..., description="Le nom scientifique du taxon à traiter")


class ExternalLink(BaseModel):
    """Un lien externe de debug (`TaxonomyModule.debug_link`), attribué à son module d'origine —
    nécessaire côté frontend pour l'associer à la bonne ligne du tableau de suivi par module
    (onglet Données), plutôt qu'une simple liste de HTML sans moyen de savoir quel module a
    produit quel lien."""

    module_id: str
    html: str


class ReferenceItem(BaseModel):
    """Une référence taxonomique individuelle (`module.render_bioref`), attribuée à son module
    d'origine — pendant structuré de `GenerateResponse.references_wikitext` qui permet au
    frontend de cocher/décocher chaque référence plutôt que de recevoir uniquement le bloc déjà
    joint (voir l'onglet Wikitexte > Références taxonomiques)."""

    module_id: str
    wikitext: str
    default_checked: bool = True
    """False si le domaine déclaré du module (`ModuleMeta.domains`) exclut le règne retenu pour
    ce taxon (voir `organon.core.selectors.coherence.reference_module_coherente`) — reste
    cochable manuellement, seule la case initiale change."""


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
    taxon_rang: str = ""
    """`struct.taxon.rang` — rang du taxon lui-même (ex. "genre", "famille"), pas exposé
    ailleurs dans la réponse (`rank_lines` ne porte que les rangs *supérieurs*). Nécessaire côté
    frontend pour appeler `POST /api/v1/subtaxa-merge` (accord grammatical "il"/"elle" de la
    phrase introductive, voir `organon.core.rendering.subtaxa_merge`)."""
    classification_used: str
    domain_used: str
    regne: str = ""
    eteint: bool = False
    uicn_statut: str = ""
    """Code de statut de conservation UICN (LC/NT/VU/EN/CR/EW/EX/DD/NE...), rapporté par GBIF
    via `/species/{key}/iucnRedListCategory` (voir `organon.modules.gbif`) ; vide si absent."""
    vernacular_names: list[str] = []
    autres_noms: dict[str, list[str]] = {}
    """`struct.autres_noms`, fondu toutes sources confondues par statut (ex. « Recommandé ou
    typique » -> [...]) — pendant de `vernacular_names` pour les noms qu'une source qualifie
    elle-même d'un statut explicite (voir `organon.core.models.Struct.autres_noms`), affichés à
    part dans l'onglet Noms & synonymes plutôt que fondus dans `vernacular_names`."""
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
    subtaxa_liste: list[RankName] = []
    """`struct.sous_taxons.liste` telle quelle (nom/rang/auteur/eteint), sans mise en forme —
    pendant structuré de `subtaxa_wikitext` (déjà rendu en wikitexte pour une seule source).
    Permet au frontend de recouper les sous-taxons de plusieurs sources déjà résolues (voir
    `POST /api/v1/subtaxa-merge`) sans reparser `subtaxa_wikitext`."""
    references_wikitext: str = ""
    """Les références taxonomiques (liens `render_bioref` de chaque module) isolées du reste de
    `wikitext`, selon le même principe que `taxobox_wikitext`/`subtaxa_wikitext` — exclut
    volontairement le bloc `{{Autres projets}}` (Commons/Wikispecies/Wiktionnaire), qui n'est
    pas une référence taxonomique au sens strict. Dérivé de `reference_items` (tri alphabétique
    + jointure) ; conservé pour compatibilité avec les appelants qui consomment déjà ce bloc."""
    reference_items: list[ReferenceItem] = []
    """Pendant structuré de `references_wikitext` : une entrée par ligne de référence plutôt
    qu'un bloc déjà joint, pour permettre au frontend de cocher/décocher chaque référence
    individuellement (le backend n'a aucun moyen de détecter automatiquement une source
    incohérente, donc toutes cochées par défaut)."""
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
    auteur_consolide: str = ""
    """`struct.taxon.auteur` une fois le vote majoritaire (ou l'imposition manuelle via
    `auteur_source`) tranché — même valeur que celle wikifiée dans `wikitext`, mais en texte
    brut : `auteur_candidats` donne le détail par module, celui-ci donne le résultat retenu."""
    auteur_resolu: str = ""
    """`struct.taxon.auteur_resolu` — version wikifiée (liens `{{auteur|...}}`, années liées) de
    `auteur_consolide`, telle qu'insérée dans le bloc `{{Taxobox taxon | ...}}` de `wikitext`.
    Exposée séparément pour que le frontend puisse reprendre l'auteur déjà wikifié d'une autre
    classification déjà préchargée (voir `resultsBySource` côté web-app) sans reconstruire le
    wikilinking à la main côté client."""
    synonymes: list[RankName] = []
    """`struct.synonymes.liste`, si un module en a rapporté (voir `synonymes_source`) —
    déjà collecté pour alimenter la section "Systématique" du wikitexte, ici exposé structuré."""
    synonymes_source: str = ""
    """Module source de `synonymes` (`struct.synonymes.source`) ; vide si aucun synonyme."""
    basionyme: Basionym | None = None
    """`struct.basionyme`, si un module en a rapporté un — `None` sinon."""
    logs: list[str] = []
    warnings: list[str] = []
    elapsed_seconds: float
    truncated: dict[str, bool] = {}
    regne_incoherences: list[RegneIncoherence] = []
    """Modules d'enrichissement dont le règne détecté diffère de celui retenu par la
    classification — signe possible d'homonymie inter-règnes (voir RegneIncoherence).
    Détection partielle : seuls quelques modules (GBIF/ITIS/WoRMS) exposent ce signal sans coût
    réseau supplémentaire ; son absence ne garantit donc pas la cohérence."""
    rang_incoherences: list[RangIncoherence] = []
    """Modules de classification concurrents (GBIF/CoL XR) dont la famille, l'ordre ou le statut
    (accepté/synonyme) détecté diffère de celui retenu — vrai désaccord taxonomique entre deux
    sources ayant chacune une valeur, jamais un trou de données (voir RangIncoherence). Détection
    partielle, comme `regne_incoherences` : son absence ne garantit pas la cohérence."""
    milieu: str = ""
    """`Struct.milieu` ('marin'/'terrestre'), copié tel quel depuis la source qui l'a détecté
    (ex. WoRMS via isMarine/isTerrestrial) ; vide si aucune source ne l'a renseigné."""
    distribution: dict[str, list[str]] = {}
    """Pour chaque module ayant rapporté une répartition géographique, la liste (triée,
    dédupliquée) des noms de pays qu'il rapporte — fusion de `DistributionEntry.certain` et
    `.uncertain` (la distinction n'est pas utile à ce niveau d'affichage synthétique)."""
    external_ids: dict[str, str] = {}
    """Pour chaque module ayant contribué à cette génération, son identifiant du taxon dans la
    base qu'il interroge (`struct.liens[module_id]['id']`, converti en texte) — pendant
    structuré des identifiants déjà présents mais noyés dans `external_links` (HTML) et
    `reference_items` (wikitext). Absent pour un module qui a contribué sans porter
    d'identifiant propre au taxon (ex. `externe`, ou `col` en cas d'homonymie non résolue, voir
    `_compute_external_ids`)."""


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
    duration_seconds: float | None = None
    """Temps écoulé entre le "running" et ce statut terminal — absent quand status == "running"."""


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
    qid: str | None = None
    """QID Wikidata, uniquement renseigné quand la recherche portait sur un item Wikidata (voir
    `organon.api.routes.search._search_by_qid`)."""
    external_ids: dict[str, str] = {}
    """Identifiants externes portés par l'item Wikidata (clé = id de module organon, ex. "gbif",
    "itis"), pour un futur branchement sur la résolution par id plutôt que par nom des modules
    d'enrichissement — non câblé pour l'instant, seulement exposé."""


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


class MergedSpeciesOut(BaseModel):
    """Un sous-taxon fusionné (voir `organon.core.rendering.subtaxa_merge.MergedSpecies`)."""

    nom: str
    rang: str
    line: str
    default_checked: bool


class MergedGroupOut(BaseModel):
    """Un groupe d'espèces rapportées par exactement le même ensemble de sources (voir
    `organon.core.rendering.subtaxa_merge.MergedGroup`)."""

    sources: list[str]
    kind: Literal["primary", "alternative"]
    intro: str
    species: list[MergedSpeciesOut]


class MergedSubtaxaResponse(BaseModel):
    """Réponse de `POST /api/v1/subtaxa-merge` (voir
    `organon.core.rendering.subtaxa_merge.merge_subtaxa`)."""

    rang_txt: str
    rang_txt_singulier: str
    pronoun: Literal["il", "elle"]
    taxon_phrase: str
    rang_names: dict[str, tuple[str, str]]
    """Nom de rang (pluriel, singulier) par clé technique de rang, pour que le frontend recalcule
    `rang_txt`/`rang_txt_singulier` au fil des cases (dé)cochées (voir
    `organon.core.rendering.subtaxa_merge.MergedSubtaxa.rang_names`)."""
    groups: list[MergedGroupOut]


class SubtaxaMergeSource(BaseModel):
    """Une source déjà résolue par le frontend (voir `GenerateResponse.subtaxa_liste`), fournie
    telle quelle à `POST /api/v1/subtaxa-merge` — aucun appel réseau supplémentaire, seulement du
    recoupement local entre listes déjà en mémoire côté client."""

    module_id: str
    liste: list[RankName] = Field(default_factory=list)


class SubtaxaMergeRequest(BaseModel):
    taxon_rang: str = Field(..., description="Rang du taxon principal (ex. 'genre', 'famille')")
    taxon_nom: str = Field(..., description="Nom du taxon principal (ex. 'Panthera')")
    regne: str = ""
    sources: list[SubtaxaMergeSource] = Field(default_factory=list)


class TaxoboxRefreshRequest(BaseModel):
    page_title: str = Field(..., description="Titre de la page Wikipédia à éditer")
    wikitext: str = Field(
        ..., description="Wikitexte complet à écrire sur la page (ex. produit par /api/v1/generate)"
    )


class TaxoboxRefreshResponse(BaseModel):
    page_title: str
    new_revision_id: int
    requested_by: str
