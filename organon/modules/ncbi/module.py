"""Logique métier du module NCBI Taxonomy. Module d'enrichissement uniquement
(`can_classify=False` — NCBI est explicitement déconseillé comme référence taxonomique) : fournit
seulement un identifiant croisé, en réutilisant nom/rang déjà connus de la classification
principale plutôt que ceux renvoyés par NCBI lui-même."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import simple_debug_link
from organon.modules.ncbi.adapter import NcbiAdapter


class NcbiModule(TaxonomyModule):
    meta = ModuleMeta(id="ncbi", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: NcbiAdapter | None = None) -> None:
        self._adapter = adapter or NcbiAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxid = await self._adapter.search_taxid(struct.taxon.nom)
        if taxid is None:
            return None

        struct.liens["ncbi"] = {"id": taxid, "nom": struct.taxon.nom, "rang": struct.taxon.rang}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("ncbi")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        return f"{{{{NCBI | {data['id']} | {cible} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "ncbi", "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={id}", "NCBI"
        )


register_module(NcbiModule)
