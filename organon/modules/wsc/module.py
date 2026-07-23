"""Logique métier du module World Spider Catalog (WSC) : classification des araignées (Araneae)
à partir de l'export CSV quotidien (voir adapter.py — aucune API REST utilisée, celle-ci exigeant
une inscription WSCA + clé personnelle, incompatible avec un service automatisé sans compte
dédié).

Le CSV ne couvre que famille/genre/espèce/sous-espèce : aucun rang supérieur à la famille n'y
figure. Le catalogue entier ne couvrant que l'ordre Araneae (classe Arachnida, embranchement
Arthropoda), cette chaîne fixe est injectée directement — même principe que
`organon.modules.powo.ranks.POWO_KINGDOM_MAP`, à une seule entrée car WCVP ne couvre que Plantae.

`can_render_external_link=False` (aucun {{Bioref}} publié) : la licence CC BY-NC-SA 4.0 de
l'export est nonCommercial, ce module n'expose donc la source qu'en classification interne, pas
en lien de citation public — voir organon/core/data/db_inventory.yaml (id: wsc).

Pas de distribution géographique portée par ce module : le champ CSV `distribution` est un texte
libre de noms de pays en anglais, sans code pays structuré (contrairement à POWO/GBIF) — aucune
table de correspondance nom-de-pays -> code n'existe dans ce dépôt, en construire une improvisée
produirait des codes inventés plutôt que dérivés d'une source fiable."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Redirection, Struct, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.common import MAX_SYNONYM_HOPS, format_auteur, simple_debug_link
from organon.modules.wsc.adapter import WscAdapter

_CHAINE_FIXE = (
    RankName(nom="Araneae", rang="ordre"),
    RankName(nom="Arachnida", rang="classe"),
    RankName(nom="Arthropoda", rang="embranchement"),
)
"""WSC ne couvre que cet unique embranchement/classe/ordre (tout le catalogue est Araneae),
absent de l'export CSV (limité à famille/genre/espèce) : injecté en dur plutôt qu'interrogé."""


def _format_auteur_wsc(row: dict) -> str | None:
    auteur, annee = row.get("author"), row.get("year")
    if not auteur:
        return None
    brut = f"{auteur}, {annee}" if annee else auteur
    if row.get("parentheses") == "1":
        brut = f"({brut})"
    return format_auteur(brut)


class WscModule(TaxonomyModule):
    meta = ModuleMeta(
        id="wsc", can_classify=True, can_render_external_link=False, domains="all", priority=990
    )

    def __init__(self, adapter: WscAdapter | None = None) -> None:
        self._adapter = adapter or WscAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        row = await self._adapter.search(struct.taxon.nom)
        if row is None:
            return None

        struct.liens["wsc"] = {"id": row["speciesId"], "nom": struct.taxon.nom}

        est_synonyme = row.get("taxonStatus") not in (None, "VALID")
        if est_synonyme:
            accepted = await self._adapter.by_id(row.get("validSpeciesId") or "")
            if accepted is None:
                return None
            nom_accepte = f"{accepted['genus']} {accepted['species']}"
            if not is_classification:
                struct.liens["wsc"]["synonyme"] = True
                struct.liens["wsc"]["nom-synonyme"] = nom_accepte
                struct.liens["wsc"]["id-synonyme"] = accepted["speciesId"]
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=nom_accepte)
                return await self._collect(struct, is_classification, options, hop=hop + 1)
            # suivre_synonymes désactivé : on continue avec les données du synonyme tel quel,
            # comme ITIS/GBIF/POWO
            row = accepted

        if not is_classification:
            return struct

        sous_espece = bool(row.get("subspecies")) and struct.taxon.nom == (
            f"{row['genus']} {row['species']} {row['subspecies']}"
        )
        struct.taxon.rang = "sous-espèce" if sous_espece else "espèce"
        struct.taxon.auteur = _format_auteur_wsc(row)
        struct.regne = "animal"
        struct.classification = "WSC"
        struct.classification_taxobox = "WSC"

        rangs: list[RankName] = []
        if sous_espece:
            rangs.append(RankName(nom=f"{row['genus']} {row['species']}", rang="espèce"))
        rangs.append(RankName(nom=row["genus"], rang="genre"))
        rangs.append(RankName(nom=row["family"], rang="famille"))
        rangs.extend(_CHAINE_FIXE)
        struct.rangs = rangs

        return struct

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "wsc", "https://wsc.nmbe.ch/species/{id}", "WSC")


register_module(WscModule)
