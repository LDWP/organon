"""Logique métier du module Reptile Database (reptile-database.reptarium.cz). `can_classify=True`
: la fiche espèce porte un champ « Higher Taxa » dont seuls la famille (toujours premier terme
de la liste) et l'ordre (vocabulaire fermé des 4 ordres de reptiles vivants) sont extraits de
façon fiable — voir `organon.modules.reptile_database.adapter._parse_higher_taxa` pour le détail
des clades intermédiaires (sous-famille, super-famille, sous-ordre...) volontairement ignorés :
rang non indiqué dans le HTML, et position incohérente d'une fiche à l'autre.

Le site n'a de fiche dédiée (`/Genus/species`) que pour le nom binomial accepté (genre +
épithète spécifique) : un nom trinomial de sous-espèce n'y correspond à rien et est donc ignoré
plutôt que d'être tronqué au hasard — cette base ne peut donc jamais classifier au rang
sous-espèce. Un nom à un seul mot (genre ou famille) n'a lui non plus aucune fiche, seulement un
formulaire de recherche listant les espèces correspondantes (voir
`ReptileDatabaseAdapter.genus_exists`/`family_exists`) : insuffisant pour classifier (pas de
rang parent extractible), mais assez pour confirmer la présence du taxon et publier une
citation ({{ReptileDB genre}}/{{ReptileDB famille}}) une fois son rang déjà résolu par un autre
module — voir `collect()`."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur
from organon.modules.reptile_database.adapter import BASE_URL, ReptileDatabaseAdapter


class ReptileDatabaseModule(TaxonomyModule):
    meta = ModuleMeta(
        id="reptile_database", can_classify=True, can_render_external_link=True, domains=["reptile"]
    )

    def __init__(self, adapter: ReptileDatabaseAdapter | None = None) -> None:
        self._adapter = adapter or ReptileDatabaseAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        taxon = struct.taxon.nom
        mots = taxon.split()
        if len(mots) == 2:
            return await self._collect_espece(struct, is_classification, *mots)
        # Le site n'a pas de fiche genre/famille (voir adapter.py), seulement un formulaire de
        # recherche : on ne peut donc pas classifier à ces rangs, uniquement y ajouter une
        # citation une fois le rang déjà résolu par un autre module de classification.
        if len(mots) == 1 and not is_classification and struct.taxon.rang in ("genre", "famille"):
            return await self._collect_taxon_superieur(struct, struct.taxon.rang, mots[0])
        return None

    async def _collect_espece(
        self, struct: Struct, is_classification: bool, genre: str, espece: str
    ) -> Struct | None:
        hit = await self._adapter.get_species(genre, espece)
        if hit is None:
            return None

        auteur = format_auteur(hit.auteur)
        struct.liens["reptile_database"] = {
            "rang": "espèce",
            "genre": genre,
            "espece": espece,
            "auteur": auteur,
        }

        if not is_classification:
            return struct
        if hit.famille is None:
            return None

        struct.taxon.rang = "espèce"
        struct.taxon.auteur = auteur
        struct.regne = "animal"
        struct.classification = "reptiledb"
        struct.classification_taxobox = "Reptile Database"

        rangs = [RankName(nom=genre, rang="genre"), RankName(nom=hit.famille, rang="famille")]
        if hit.ordre:
            rangs.append(RankName(nom=hit.ordre, rang="ordre"))
        struct.rangs = rangs

        return struct

    async def _collect_taxon_superieur(self, struct: Struct, rang: str, nom: str) -> Struct | None:
        existe = (
            await self._adapter.genus_exists(nom)
            if rang == "genre"
            else await self._adapter.family_exists(nom)
        )
        if not existe:
            return None
        struct.liens["reptile_database"] = {"rang": rang, "nom": nom}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("reptile_database")
        if not data:
            return None
        cdate = dates_recupere()
        if data["rang"] == "espèce":
            auteur = f" | {data['auteur']}" if data.get("auteur") else ""
            return (
                f"{{{{ReptileDB espèce | {data['genre']} | {data['espece']}{auteur} "
                f"| consulté le={cdate} }}}}"
            )
        modele = "ReptileDB genre" if data["rang"] == "genre" else "ReptileDB famille"
        return f"{{{{{modele} | {data['nom']} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("reptile_database")
        if not data:
            return None
        if data["rang"] == "espèce":
            url = f"{BASE_URL}/{data['genre']}/{data['espece']}"
        else:
            champ = "genus" if data["rang"] == "genre" else "taxon"
            url = (
                f"{BASE_URL}/advanced_search?{champ}={data['nom']}&exact%5B%5D={champ}"
                "&ok=Search&do=AdvancedSearchForm-submit"
            )
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>Reptile Database</a>"


register_module(ReptileDatabaseModule)
