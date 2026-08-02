"""Logique métier du module Reptile Database (reptile-database.reptarium.cz). `can_classify=True`
: la fiche espèce porte un champ « Higher Taxa » dont seuls la famille (toujours premier terme
de la liste) et l'ordre (vocabulaire fermé des 4 ordres de reptiles vivants) sont extraits de
façon fiable — voir `organon.modules.reptile_database.adapter._parse_higher_taxa` pour le détail
des clades intermédiaires (sous-famille, super-famille, sous-ordre...) volontairement ignorés :
rang non indiqué dans le HTML, et position incohérente d'une fiche à l'autre.

Le site n'indexe que le nom binomial accepté (genre + épithète spécifique) : un nom qui n'est
pas exactement à deux mots (genre seul, trinomial de sous-espèce, etc.) n'a pas de fiche
`/Genus/species` correspondante et est donc ignoré ici plutôt que d'être tronqué au hasard —
cette base ne peut donc jamais classifier au rang sous-espèce."""

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
        if len(mots) != 2:
            return None
        genre, espece = mots

        hit = await self._adapter.get_species(genre, espece)
        if hit is None:
            return None

        auteur = format_auteur(hit.auteur)
        struct.liens["reptile_database"] = {"genre": genre, "espece": espece, "auteur": auteur}

        if not is_classification:
            return struct
        if hit.famille is None:
            return None

        struct.taxon.rang = "espèce"
        struct.taxon.auteur = auteur
        struct.regne = "animal"
        struct.classification = "Reptile Database"
        struct.classification_taxobox = "Reptile Database"

        rangs = [RankName(nom=genre, rang="genre"), RankName(nom=hit.famille, rang="famille")]
        if hit.ordre:
            rangs.append(RankName(nom=hit.ordre, rang="ordre"))
        struct.rangs = rangs

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("reptile_database")
        if not data:
            return None
        cdate = dates_recupere()
        auteur = f" | {data['auteur']}" if data.get("auteur") else ""
        return (
            f"{{{{ReptileDB espèce | {data['genre']} | {data['espece']}{auteur} "
            f"| consulté le={cdate} }}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("reptile_database")
        if not data:
            return None
        url = f"{BASE_URL}/{data['genre']}/{data['espece']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>Reptile Database</a>"


register_module(ReptileDatabaseModule)
