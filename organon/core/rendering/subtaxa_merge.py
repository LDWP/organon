"""Fusion des sous-taxons rapportés par plusieurs sources de classification déjà résolues pour
un même taxon (voir `organon.core.models.SubTaxonList` : chaque module de classification résout
sa propre liste indépendamment, sans identifiant stable comparable entre modules — pas de clé
GBIF ou équivalent portée par `RankName`).

Recoupement des espèces entre sources par nom EXACT (`RankName.nom`) uniquement : deux graphies
différentes du même taxon (accentuation, orthographe, ordre auteur/nom) ne seront pas reconnues
comme identiques. Limitation assumée plutôt qu'un rapprochement flou qui masquerait des faux
positifs — documentée ici et à répercuter dans toute UI qui consomme `merge_subtaxa`.

Les sources sont regroupées par ensemble EXACT d'espèces qu'elles rapportent : deux sources ne
sont fusionnées en un seul groupe que si elles s'accordent parfaitement (même ensemble de noms).
Dès qu'une source diverge ne serait-ce que d'une espèce, elle forme son propre groupe avec sa
liste COMPLÈTE — jamais un reliquat "N espèces en plus" par rapport à un autre groupe. Les
groupes sont ordonnés par taille décroissante (le plus d'espèces d'abord), à égalité par ordre
d'apparition des sources dans `sources` — le premier groupe sert de "primary" (coché par défaut,
phrase d'ouverture nommant le taxon), les suivants "alternative" (décochés par défaut, phrase
reprenant le pronom anaphorique).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from organon.core.models import RankName
from organon.core.rendering.grammar import (
    load_rank_table,
    wp_le_rang,
    wp_met_italiques,
    wp_nom_rang,
)
from organon.core.rendering.sections import compute_rang_txt, render_subtaxon_line
from organon.core.rendering.support import dates_recupere

GroupKind = Literal["primary", "alternative"]


@dataclass
class MergedSpecies:
    nom: str
    line: str
    """Ligne wikitexte déjà mise en forme (voir `sections.render_subtaxon_line`)."""
    default_checked: bool


@dataclass
class MergedGroup:
    sources: list[str]
    """Sources qui rapportent EXACTEMENT ce même ensemble d'espèces, dans l'ordre où elles
    apparaissent dans `sources` (paramètre de `merge_subtaxa`), pas un ordre alphabétique."""
    kind: GroupKind
    """"primary" : le premier groupe (le plus grand) — coché par défaut, sert d'ancre à la
    phrase introductive. "alternative" : liste complète mais divergente rapportée par une ou
    plusieurs autres sources — décochée par défaut, l'utilisateur choisit laquelle retenir."""
    intro: str
    """Clause "Selon {{Bioref|...}} et {{Bioref|...}}" (plusieurs sources) ou "Pour {{Bioref|...}}"
    (une seule) déjà mise en forme avec citation Bioref par source, même convention que
    `render_inf` ("Selon {{Bioref|module|date}} :"). Ne porte volontairement pas le nombre
    d'espèces ni le rang : ce compte dépend des cases cochées côté frontend (voir
    `MergedSpecies.default_checked`), recalculé there sans nouvel appel réseau."""
    species: list[MergedSpecies]


@dataclass
class MergedSubtaxa:
    rang_txt: str
    rang_txt_singulier: str
    """Forme singulière de `rang_txt` (ex. "espèce" pour "espèces") — nécessaire pour l'accord
    du compte d'espèces quand un groupe n'en contient qu'une (le compte étant réactif aux cases
    cochées côté frontend, "espèces"/"autres" ne peuvent pas être figés dans une phrase déjà
    rendue ici, voir `MergedGroup.intro`)."""
    pronoun: Literal["il", "elle"]
    """Pronom accordé au rang du taxon principal (ex. "le genre" -> "il", "la famille" ->
    "elle"), pour la phrase "{Selon|Pour} ..., {pronoun} comprend N ..." — utilisé pour tous les
    groupes SAUF le premier (voir `taxon_phrase`)."""
    taxon_phrase: str
    """Sujet explicite nommé du taxon (ex. "le genre ''Panthera''"), utilisé uniquement dans la
    phrase du premier groupe ("Selon SourceA et SourceB, le genre X comprend N espèces") ; les
    groupes suivants reprennent l'anaphore `pronoun` ("Pour SourceC, il comprend...") plutôt que
    de renommer le taxon à chaque phrase."""
    groups: list[MergedGroup]


def _pronoun(taxon_rang: str) -> Literal["il", "elle"]:
    table = load_rank_table()
    if taxon_rang not in table.ranks:
        return "il"
    return "il" if table.ranks[taxon_rang].genre == "masculin" else "elle"


def _taxon_phrase(taxon_rang: str, taxon_nom: str, regne: str) -> str:
    article = wp_le_rang(taxon_rang)
    rang_nom = wp_nom_rang(taxon_rang, lien=False, maj=False, plur=False)
    cible = wp_met_italiques(taxon_nom, taxon_rang, regne)
    if article == "NOTFOUND" or rang_nom == "NOTFOUND":
        return cible
    return f"{article}{rang_nom} {cible}"


def _join_et(items: list[str]) -> str:
    """Même convention de jonction que `sections.compute_rang_txt` : virgules, "et" avant le
    dernier élément."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    txt = items[0]
    for i in range(1, len(items)):
        txt += " et " + items[i] if i == len(items) - 1 else ", " + items[i]
    return txt


def _intro(sources_list: list[str], cdate: str) -> str:
    citations = [f"{{{{Bioref|{s}|{cdate}}}}}" for s in sources_list]
    if len(citations) == 1:
        return f"Pour {citations[0]}"
    return "Selon " + _join_et(citations)


def merge_subtaxa(
    taxon_rang: str, taxon_nom: str, regne: str, sources: list[tuple[str, list[RankName]]]
) -> MergedSubtaxa:
    source_order: list[str] = []
    source_liste: dict[str, list[RankName]] = {}
    name_to_species: dict[str, RankName] = {}

    for module_id, liste in sources:
        if module_id in source_liste:
            continue
        source_order.append(module_id)
        source_liste[module_id] = liste
        for sp in liste:
            if sp.nom not in name_to_species:
                name_to_species[sp.nom] = sp

    all_species = [name_to_species[n] for n in name_to_species]
    rang_txt, rang_txt_singulier, rang_defaut = compute_rang_txt(all_species)

    # Regroupe les sources qui rapportent EXACTEMENT le même ensemble d'espèces (par nom).
    group_order: list[frozenset[str]] = []
    group_sources: dict[frozenset[str], list[str]] = {}
    for module_id in source_order:
        key = frozenset(sp.nom for sp in source_liste[module_id])
        if key not in group_sources:
            group_sources[key] = []
            group_order.append(key)
        group_sources[key].append(module_id)

    # Le plus grand groupe (le plus d'espèces) en premier ; à égalité, ordre d'apparition de sa
    # première source dans `sources`.
    group_order.sort(key=lambda k: (-len(k), source_order.index(group_sources[k][0])))

    cdate = dates_recupere()
    groups = []
    for i, key in enumerate(group_order):
        ordered_sources = group_sources[key]
        kind: GroupKind = "primary" if i == 0 else "alternative"
        # Liste complète telle que rapportée par la première source du groupe (toutes les
        # sources du groupe s'accordent par construction sur ce même ensemble de noms).
        species_names = sorted(sp.nom for sp in source_liste[ordered_sources[0]])
        groups.append(
            MergedGroup(
                sources=ordered_sources,
                kind=kind,
                intro=_intro(ordered_sources, cdate),
                species=[
                    MergedSpecies(
                        nom=nom,
                        line=render_subtaxon_line(name_to_species[nom], regne, rang_defaut, taxon_rang),
                        default_checked=(kind == "primary"),
                    )
                    for nom in species_names
                ],
            )
        )

    return MergedSubtaxa(
        rang_txt=rang_txt,
        rang_txt_singulier=rang_txt_singulier,
        pronoun=_pronoun(taxon_rang),
        taxon_phrase=_taxon_phrase(taxon_rang, taxon_nom, regne),
        groups=groups,
    )
