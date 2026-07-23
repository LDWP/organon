"""Logique métier du module Reptile Database (reptile-database.reptarium.cz). Module
d'enrichissement uniquement (`can_classify=False`), limité au domaine reptile.

Le site n'indexe que le nom binomial accepté (genre + épithète spécifique) : un nom qui n'est
pas exactement à deux mots (genre seul, trinomial de sous-espèce, etc.) n'a pas de fiche
`/Genus/species` correspondante et est donc ignoré ici plutôt que d'être tronqué au hasard."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.reptile_database.adapter import BASE_URL, ReptileDatabaseAdapter


class ReptileDatabaseModule(TaxonomyModule):
    meta = ModuleMeta(
        id="reptile_database", can_classify=False, can_render_external_link=True, domains=["reptile"]
    )

    def __init__(self, adapter: ReptileDatabaseAdapter | None = None) -> None:
        self._adapter = adapter or ReptileDatabaseAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        mots = taxon.split()
        if len(mots) != 2:
            return None
        genre, espece = mots

        hit = await self._adapter.get_species(genre, espece)
        if hit is None:
            return None
        _, auteur = hit

        struct.liens["reptile_database"] = {"genre": genre, "espece": espece, "auteur": auteur}
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
