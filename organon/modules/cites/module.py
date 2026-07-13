"""Logique métier du module CITES. Module d'enrichissement uniquement (pas de classification) :
alimente `{{Taxobox CITES}}` (voir `organon.core.rendering.sections.render_taxobox`) et les
noms vernaculaires français."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.cites.adapter import CitesAdapter
from organon.modules.common import format_auteur, simple_debug_link


class CitesModule(TaxonomyModule):
    meta = ModuleMeta(id="cites", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: CitesAdapter | None = None) -> None:
        self._adapter = adapter or CitesAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None  # CITES ne fournit jamais de classification

        candidates = await self._adapter.autocomplete(struct.taxon.nom)
        match = next((c for c in candidates if c.get("full_name") == struct.taxon.nom), None)
        if match is None:
            return None

        detail = await self._adapter.taxon_concept(match["id"])
        if detail is None or not detail.get("cites_listings"):
            return None

        listing = detail["cites_listings"][0]
        struct.liens["cites"] = {
            "id": match["id"],
            "nom": detail["full_name"],
            "auteur": format_auteur(detail.get("author_year")),
            "annexe": listing.get("species_listing_name"),
            "date": listing.get("effective_at_formatted"),
        }

        vernaculaire: list[str] = []
        for cn in detail.get("common_names") or []:
            if cn.get("lang") == "French":
                vernaculaire.extend(cn.get("names", "").split(", "))
        if vernaculaire:
            struct.vernaculaire["CITES espèce"] = vernaculaire

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("cites")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        auteur = data.get("auteur") or ""
        return f"{{{{CITES species+ | {data['id']} | {cible} | {auteur} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "cites", "https://www.speciesplus.net/#/taxon_concepts/{id}/legal", "CITES species+"
        )


register_module(CitesModule)
