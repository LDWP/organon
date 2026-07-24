"""Fusion des sous-taxons rapportés par plusieurs sources de classification déjà résolues pour
un même taxon (voir `organon.core.models.SubTaxonList` : chaque module de classification résout
sa propre liste indépendamment, sans identifiant stable comparable entre modules — pas de clé
GBIF ou équivalent portée par `RankName`).

Recoupement des espèces entre sources par nom EXACT (`RankName.nom`) uniquement : deux graphies
différentes du même taxon (accentuation, orthographe, ordre auteur/nom) ne seront pas reconnues
comme identiques. Limitation assumée plutôt qu'un rapprochement flou qui masquerait des faux
positifs — documentée ici et à répercuter dans toute UI qui consomme `merge_subtaxa`.

Les espèces sont groupées par ensemble EXACT de sources qui les rapportent, puis les groupes
sont ordonnés : le plus grand groupe en premier (l'« ancre »), puis, en boucle, le plus grand
groupe restant partageant au moins une source avec l'union des sources déjà placées (glouton :
équivaut à un parcours en largeur des groupes connectés par source partagée), puis les groupes
restants qui démarrent une nouvelle composante disjointe, plus grand d'abord.
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

GroupKind = Literal["anchor", "autres", "disjoint"]


@dataclass
class MergedSpecies:
    nom: str
    line: str
    """Ligne wikitexte déjà mise en forme (voir `sections.render_subtaxon_line`)."""
    default_checked: bool


@dataclass
class MergedGroup:
    sources: list[str]
    """Sources qui rapportent exactement ce groupe d'espèces, dans l'ordre où elles apparaissent
    dans `sources` (paramètre de `merge_subtaxa`), pas un ordre alphabétique."""
    kind: GroupKind
    """"anchor" : le premier groupe (le plus grand) — sert d'ancre à la phrase introductive.
    "autres" : partage au moins une source avec un groupe déjà placé (case à cocher par défaut).
    "disjoint" : ne partage aucune source avec ce qui précède (décoché par défaut)."""
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
    name_order: list[str] = []
    name_to_species: dict[str, RankName] = {}
    name_to_sources: dict[str, list[str]] = {}

    for module_id, liste in sources:
        if module_id not in source_order:
            source_order.append(module_id)
        for sp in liste:
            if sp.nom not in name_to_species:
                name_to_species[sp.nom] = sp
                name_to_sources[sp.nom] = []
                name_order.append(sp.nom)
            name_to_sources[sp.nom].append(module_id)

    all_species = [name_to_species[n] for n in name_order]
    rang_txt, rang_txt_singulier, rang_defaut = compute_rang_txt(all_species)

    group_order: list[frozenset[str]] = []
    group_names: dict[frozenset[str], list[str]] = {}
    for nom in name_order:
        key = frozenset(name_to_sources[nom])
        if key not in group_names:
            group_names[key] = []
            group_order.append(key)
        group_names[key].append(nom)

    def largest(candidates: list[frozenset[str]]) -> frozenset[str]:
        return max(candidates, key=lambda k: (len(group_names[k]), -group_order.index(k)))

    placed: list[tuple[frozenset[str], GroupKind]] = []
    seen_sources: set[str] = set()
    remaining = list(group_order)

    while remaining:
        sharing = [k for k in remaining if k & seen_sources]
        if not placed:
            pick = largest(remaining)
            kind: GroupKind = "anchor"
        elif sharing:
            pick = largest(sharing)
            kind = "autres"
        else:
            pick = largest(remaining)
            kind = "disjoint"
        placed.append((pick, kind))
        remaining.remove(pick)
        seen_sources |= pick

    cdate = dates_recupere()
    groups = []
    for key, kind in placed:
        ordered_sources = sorted(key, key=source_order.index)
        groups.append(
            MergedGroup(
                sources=ordered_sources,
                kind=kind,
                intro=_intro(ordered_sources, cdate),
                species=[
                    MergedSpecies(
                        nom=nom,
                        line=render_subtaxon_line(name_to_species[nom], regne, rang_defaut),
                        default_checked=(kind != "disjoint"),
                    )
                    for nom in group_names[key]
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
