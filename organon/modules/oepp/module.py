"""Logique métier du module OEPP/EPPO (Global Database, organismes réglementés — ravageurs,
maladies, mauvaises herbes). Module d'enrichissement uniquement (`can_classify=False`).
Réutilise le rang déjà connu de la classification principale : l'EPPO Global Database ne fournit
pas de rang structuré exploitable ici."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.oepp.adapter import OeppAdapter


class OeppModule(TaxonomyModule):
    meta = ModuleMeta(id="oepp", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: OeppAdapter | None = None) -> None:
        self._adapter = adapter or OeppAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        results = await self._adapter.search(taxon)
        match = next((r for r in results if r.get("f") == taxon), None)
        if match is None:
            return None

        blob: dict = {"id": match["e"], "nom": taxon}

        detail = await self._adapter.taxon_detail(match["e"])
        if detail["auteur"]:
            blob["auteur"] = format_auteur(detail["auteur"])
        if detail["vernaculaire_fr"]:
            struct.vernaculaire["OEPP"] = detail["vernaculaire_fr"]

        struct.liens["oepp"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("oepp")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        auteur = data.get("auteur") or ""
        return f"{{{{OEPP | {data['id']} | {cible} | {auteur} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "oepp", "https://gd.eppo.int/taxon/{id}", "OEPP")


register_module(OeppModule)
