"""Modèle de données typé décrivant l'état accumulé pendant la génération d'un article : le
taxon demandé, sa classification, les données brutes par module, et tout ce que le rendu
final consomme.

Pydantic plutôt que des dicts non typés : toute donnée mal formée lève une `ValidationError`
explicite à la collecte, au lieu d'une conversion silencieuse ou d'un plantage tardif au
rendu. `liens` garde volontairement un format libre par module (chaque module type sa propre
écriture avec son propre sous-modèle Pydantic — voir `organon.modules.*`) plutôt qu'un schéma
unique qui devrait anticiper les champs des ~37 modules à l'avance.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaxonInfo(BaseModel):
    """struct['taxon'] — nom/rang/auteur du taxon demandé, tel que résolu par le module de
    classification (peut différer du nom initialement demandé si un synonyme a été suivi)."""

    nom: str
    rang: str | None = None
    auteur: str | None = None
    eteint: bool | None = None
    auteur_resolu: str | None = None
    """Texte d'auteur wikifié (auteurs connus liés, années liées, {{auteur}} pour le reste) —
    calculé une seule fois pendant l'orchestration par
    `organon.core.rendering.authors.resoudre_auteur_principal` (l'appel de résolution botanique/
    zoologique/procaryote nécessite de connaître `regne`, déjà résolu à ce stade). `None` tant
    que non calculé ; les deux points de rendu affichant l'auteur du taxon principal
    (`sections.py`) lisent ce champ plutôt que `auteur` brut."""


class RankName(BaseModel):
    """Un élément de struct['rangs'] (taxons parents, pour la taxobox) ou de
    struct['sous-taxons']['liste'] / struct['synonymes']['liste'] (mêmes champs)."""

    nom: str
    rang: str | None = None
    auteur: str | None = None
    eteint: bool | None = None


class Redirection(BaseModel):
    """struct['redirection'] — nom d'origine si un synonyme a été suivi."""

    nom: str


class Basionym(BaseModel):
    """struct['basionyme'] — informations sur le basionyme. `source` = nom technique du module
    qui a fourni l'info (pour sourçage Bioref)."""

    nom: str
    auteur: str | None = None
    source: str


class TypeTaxon(BaseModel):
    """struct['type'] — taxon-type (rang inférieur qui constitue la création du taxon)."""

    nom: str
    rang: str | None = None
    auteur: str | None = None
    source: str


class SubTaxonList(BaseModel):
    """struct['sous-taxons'] — liste des taxons de rang inférieur."""

    liste: list[RankName] = Field(default_factory=list)
    source: str | None = None
    coupe: bool = False
    """True si la liste a été tronquée par l'option 'limite-listes'."""


class SynonymList(BaseModel):
    """struct['synonymes'] — liste des synonymes du taxon."""

    liste: list[RankName] = Field(default_factory=list)
    source: str | None = None
    coupe: bool = False


class Etymology(BaseModel):
    """struct['etymologie']."""

    texte: str
    source: str


class DistributionEntry(BaseModel):
    """Un élément de struct['distribution'][module_id]. Les valeurs sont des codes pays ; le
    dict conserve le code comme clé ET valeur (ex. `{"MG": "MG"}`), ce qui permet de tester
    l'appartenance d'un code par simple présence de clé sans construire un `set` séparé."""

    certain: dict[str, str] = Field(default_factory=dict)
    uncertain: dict[str, str] = Field(default_factory=dict)


class RegneIncoherence(BaseModel):
    """Signale qu'un module d'enrichissement (`is_classification=False`) a trouvé un règne
    différent de `struct.regne` retenu par le module de classification — signe possible d'une
    homonymie inter-règnes (ex. "Morus" = mûrier chez les botanistes vs fou de Bassan chez les
    zoologistes) plutôt que d'un enrichissement du même taxon.

    Détecté uniquement quand le module expose déjà ce signal sans appel réseau supplémentaire
    (le règne était déjà présent dans la réponse utilisée pour la recherche du nom) : ce n'est
    donc pas une détection exhaustive, seulement honnête sur ce qu'elle couvre.
    """

    module: str
    regne_suggere: str
    regne_retenu: str


class Struct(BaseModel):
    """Objet mutable unique passé par référence tout au long du pipeline (résolution de la
    classification -> enrichissement par les modules -> rendu) — un choix pragmatique adapté
    à ce flux séquentiel, pas une réécriture en style event-sourcing/immuable qui
    n'apporterait rien ici.

    `liens` garde volontairement un format libre par module : chaque module écrit sa propre
    forme sous `liens[<id-module>]`. Les modules "spéciaux" `externe` (liens hors Wikipédia :
    Wikidata, Commons, Species) et `fin` (portails/catégories) suivent la même convention.
    Chaque module type sa propre écriture avec un sous-modèle Pydantic (voir
    organon.modules.*) avant de l'assigner ici ; Struct lui-même reste générique pour ne pas
    devoir connaître à l'avance la liste des ~37 modules.
    """

    taxon: TaxonInfo
    classification: str = ""
    classification_taxobox: str = ""
    domaine: str = "*"
    regne: str = ""
    redirection: Redirection | None = None
    rangs: list[RankName] = Field(default_factory=list)
    """Taxons supérieurs, triés dans l'ordre croissant des rangs (du plus proche au plus
    éloigné du taxon demandé) — l'ordre est sémantiquement significatif pour la taxobox."""

    liens: dict[str, dict[str, Any]] = Field(default_factory=dict)

    basionyme: Basionym | None = None
    sous_taxons: SubTaxonList | None = None
    vernaculaire: dict[str, list[str]] = Field(default_factory=dict)
    """struct['vernaculaire'][nom-technique-module] -> liste de noms vernaculaires."""

    etymologie: Etymology | None = None
    originale: str | list[str] | None = None
    synonymes: SynonymList | None = None
    type_taxon: TypeTaxon | None = None
    distribution: dict[str, DistributionEntry] = Field(default_factory=dict)

    cacher_regne: bool = False
    """Certains modules (ex. lorsqu'un synonyme change de règne) peuvent demander à masquer
    le champ 'règne' de la taxobox plutôt que d'afficher une valeur incohérente."""

    image: dict[str, str] | None = None
    """struct['image'] — clés 'image'/'legende' pour la taxobox, si une source en fournit."""

    milieu: str | None = None
    """Milieu écologique du taxon ('marin' / 'terrestre'), quand une source le fournit (ex.
    WoRMS via isMarine/isTerrestrial) ; None si inconnu. Utilisé par le sélecteur de portails
    pour décider de l'ajout de {{Portail biologie marine}} (voir
    `organon.core.selectors.rules.portails`)."""
