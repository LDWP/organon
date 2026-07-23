"""Logique métier du module The Taxonomicon (taxonomicon.taxonomy.nl / Systema Naturae 2000).
Module d'enrichissement uniquement (`can_classify=False`) : réutilise le rang déjà connu de la
classification principale, comme `organon.modules.oepp` — Taxonomicon ne fournit pas de rang
structuré exploitable côté scraping (voir adapter.py).

Ne retient que les correspondances valides ("Valid", au sens de la classification Systema
Naturae 2000 du site — exclut les entrées "nom. inval.") dont le nom correspond exactement au
taxon demandé, comme `organon.modules.eflora`. L'auteur complet nécessite un second appel vers
la fiche de nomenclature, comme `organon.modules.oepp`."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.taxonomicon.adapter import TaxonomiconAdapter


class TaxonomiconModule(TaxonomyModule):
    meta = ModuleMeta(
        id="taxonomicon", can_classify=False, can_render_external_link=True, domains="all"
    )

    def __init__(self, adapter: TaxonomiconAdapter | None = None) -> None:
        self._adapter = adapter or TaxonomiconAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        hits = await self._adapter.search(taxon)
        match = next((hit for hit in hits if hit[0] == "Valid" and hit[2] == taxon), None)
        if match is None:
            return None
        _, taxon_id, _ = match

        blob: dict = {"id": taxon_id, "nom": taxon}
        auteur = await self._adapter.author_citation(taxon_id)
        if auteur:
            blob["auteur"] = format_auteur(auteur)

        struct.liens["taxonomicon"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("taxonomicon")
        if not data:
            return None
        cdate = dates_recupere()
        nom = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            nom += " " + data["auteur"]
        return f"{{{{Taxonomicon | {data['id']} | {nom} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct,
            "taxonomicon",
            "http://taxonomicon.taxonomy.nl/TaxonTree.aspx?id={id}",
            "Taxonomicon",
        )


register_module(TaxonomiconModule)
