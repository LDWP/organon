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

`reconcile_synonym_groups` (voir plus bas) est une seconde phase optionnelle, asynchrone, qui
départage les cas où deux sources rapportent le même NOMBRE d'espèces mais divergent sur un ou
plusieurs noms à cause d'une synonymie (ex. Discussion Projet:Biologie/Organon #30 : GBIF et POWO
rapportent chacun 22 espèces pour *Anthoshorea*, une seule diffère de graphie entre les deux).
Cette phase résout les noms orphelins via un identifiant tiers (COL XR, voir
`organon.modules.col_xr.lookup.resolve_col_xr_concept_id`, injecté par l'appelant) et ne fusionne
que si la correspondance est une bijection complète et vérifiée — jamais par ressemblance de nom
seule.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from organon.core.models import RankName
from organon.core.rendering.grammar import (
    load_rank_table,
    wp_le_rang,
    wp_met_italiques,
    wp_nom_rang,
)
from organon.core.rendering.sections import (
    compute_rang_names,
    compute_rang_txt,
    join_et,
    render_subtaxon_line,
)
from organon.core.rendering.support import dates_recupere

GroupKind = Literal["primary", "alternative"]


@dataclass
class MergedSpecies:
    nom: str
    rang: str
    """Clé technique du rang (ex. "sous-espèce") — permet au frontend de recalculer
    `MergedSubtaxa.rang_txt`/`rang_txt_singulier` au fil des cases cochées via `rang_names`,
    plutôt que de figer un texte qui ne refléterait que l'ensemble complet des sources."""
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
    rang_names: dict[str, tuple[str, str]]
    """Nom de rang (pluriel, singulier) par clé technique de rang, pour l'ensemble des espèces
    toutes sources confondues (voir `sections.compute_rang_names`). `rang_txt`/`rang_txt_singulier`
    ci-dessus figent le texte pour l'ensemble complet ; cette table permet au frontend de
    recalculer ce texte au fil des cases (dé)cochées — sinon la phrase citerait un rang (ex.
    "variétés") qui a été intégralement décoché par l'utilisateur."""
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


def _intro(sources_list: list[str], cdate: str) -> str:
    citations = [f"{{{{Bioref|{s}|{cdate}}}}}" for s in sources_list]
    if len(citations) == 1:
        return f"Pour {citations[0]}"
    return "Selon " + join_et(citations)


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
    rang_names = compute_rang_names(all_species)

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
                        rang=name_to_species[nom].rang or rang_defaut,
                        line=render_subtaxon_line(
                            name_to_species[nom], regne, rang_defaut, taxon_rang
                        ),
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
        rang_names=rang_names,
        groups=groups,
    )


def _merge_pair(
    primary: MergedGroup, secondary: MergedGroup, source_order: list[str], pairing: dict[str, str]
) -> MergedGroup:
    """Fusionne deux groupes de même taille dont chaque nom orphelin de `primary` a été apparié à
    l'unique nom homologue de `secondary` (bijection déjà vérifiée par l'appelant, voir
    `reconcile_synonym_groups`). `pairing` : nom (dans `primary`) -> nom homologue (dans
    `secondary`). `kind`/`intro` sont des valeurs provisoires, recalculées par l'appelant une fois
    l'ordre final des groupes connu."""
    primary_by_nom = {s.nom: s for s in primary.species}
    secondary_by_nom = {s.nom: s for s in secondary.species}
    species = [s for nom, s in primary_by_nom.items() if nom in secondary_by_nom]
    species += [primary_by_nom[nom] for nom in pairing]
    return MergedGroup(
        sources=sorted(primary.sources + secondary.sources, key=source_order.index),
        kind="alternative",
        intro="",
        species=sorted(species, key=lambda s: s.nom),
    )


def _resolved_ids(names: set[str], ids: list[str | None]) -> dict[str, str] | None:
    """None dès qu'un nom ne s'est pas résolu — un identifiant absent invalide toute la
    correspondance pour cette paire de groupes (voir `reconcile_synonym_groups`)."""
    result: dict[str, str] = {}
    for nom, cid in zip(names, ids, strict=True):
        if cid is None:
            return None
        result[nom] = cid
    return result


async def reconcile_synonym_groups(
    groups: list[MergedGroup],
    source_order: list[str],
    resolve: Callable[[str], Awaitable[str | None]],
) -> list[MergedGroup]:
    """Départage par synonymie vérifiée les groupes que `merge_subtaxa` a laissés séparés faute
    d'accord exact sur les noms, quand deux groupes rapportent le même NOMBRE d'espèces (voir
    Discussion Projet:Biologie/Organon #30 : GBIF et POWO rapportent chacun 22 espèces pour
    *Anthoshorea*, une seule diffère de graphie entre les deux, empêchant sinon la phrase unifiée).

    `resolve(nom)` doit renvoyer un identifiant externe stable (ex. COL XR, voir
    `organon.modules.col_xr.lookup.resolve_col_xr_concept_id`) ou `None` si non résolu — injecté
    pour ne pas coupler ce module, autrement pur, à un module réseau précis (voir l'appelant,
    `organon.api.routes.subtaxa_merge`). Ne fusionne QUE si chaque nom orphelin d'un côté a un et
    un seul homologue de l'autre côté avec le même identifiant résolu (bijection complète, aucun
    `None`, aucune ambiguïté) — jamais par ressemblance de nom seule, même logique de prudence que
    `merge_subtaxa` (voir docstring de module).
    """
    if len(groups) < 2:
        return list(groups)

    working = list(groups)
    cache: dict[str, str | None] = {}

    async def resolved(nom: str) -> str | None:
        if nom not in cache:
            cache[nom] = await resolve(nom)
        return cache[nom]

    merged_once = True
    while merged_once:
        merged_once = False
        for i in range(len(working)):
            for j in range(i + 1, len(working)):
                ga, gb = working[i], working[j]
                if len(ga.species) != len(gb.species) or not ga.species:
                    continue
                a_first = source_order.index(ga.sources[0])
                b_first = source_order.index(gb.sources[0])
                primary, secondary = (ga, gb) if a_first <= b_first else (gb, ga)

                primary_names = {s.nom for s in primary.species}
                secondary_names = {s.nom for s in secondary.species}
                only_primary = primary_names - secondary_names
                only_secondary = secondary_names - primary_names
                if not only_primary:
                    continue  # groupes déjà identiques : ne devrait pas arriver (garde-fou)

                ids_primary, ids_secondary = await asyncio.gather(
                    asyncio.gather(*(resolved(n) for n in only_primary)),
                    asyncio.gather(*(resolved(n) for n in only_secondary)),
                )
                id_of_primary = _resolved_ids(only_primary, ids_primary)
                id_of_secondary = _resolved_ids(only_secondary, ids_secondary)
                if id_of_primary is None or id_of_secondary is None:
                    continue

                name_of_id_secondary: dict[str, str] = {}
                ambiguous = False
                for nom, cid in id_of_secondary.items():
                    if cid in name_of_id_secondary:
                        ambiguous = True
                        break
                    name_of_id_secondary[cid] = nom
                if ambiguous or any(
                    cid not in name_of_id_secondary for cid in id_of_primary.values()
                ):
                    continue

                pairing = {nom: name_of_id_secondary[cid] for nom, cid in id_of_primary.items()}
                if len(set(pairing.values())) != len(pairing):
                    continue  # bijection stricte : pas deux orphelins vers le même homologue

                working[i] = _merge_pair(primary, secondary, source_order, pairing)
                del working[j]
                merged_once = True
                break
            if merged_once:
                break

    cdate = dates_recupere()
    working.sort(key=lambda g: (-len(g.species), source_order.index(g.sources[0])))
    return [
        MergedGroup(
            sources=g.sources,
            kind="primary" if i == 0 else "alternative",
            intro=_intro(g.sources, cdate),
            species=[
                MergedSpecies(nom=s.nom, rang=s.rang, line=s.line, default_checked=(i == 0))
                for s in g.species
            ],
        )
        for i, g in enumerate(working)
    ]
