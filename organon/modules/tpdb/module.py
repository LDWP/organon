"""Logique métier du module TPDB (Paleobiology Database) : enrichissement uniquement
(`can_classify=False`).

Le rang et l'auteur sont récupérés via un second appel à `taxa/single.json` (voir adapter.py)
après la recherche initiale. Le statut « non valide » (`nv`, recombinaison/synonyme) est
capturé mais non exploité par `render_bioref()` — le modèle `{{TPDB}}` ne gère pas ce cas."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.tpdb.adapter import TpdbAdapter
from organon.modules.tpdb.ranks import tpdb_rang


class TpdbModule(TaxonomyModule):
    meta = ModuleMeta(id="tpdb", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: TpdbAdapter | None = None) -> None:
        self._adapter = adapter or TpdbAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        results = await self._adapter.search(taxon)
        if not results:
            return None

        # si plusieurs entrées de recherche partagent exactement ce nom, la dernière l'emporte.
        record_id: str | None = None
        for r in results:
            if r.get("name") == taxon:
                record_id = r.get("record_id")
        if record_id is None:
            return None

        blob: dict = {"id": record_id, "nom": taxon}

        detail = await self._adapter.taxon_by_name(taxon)
        if detail is not None:
            if detail.get("taxon_name"):
                blob["nom"] = detail["taxon_name"]
            if detail.get("taxon_rank"):
                blob["rang"] = tpdb_rang(detail["taxon_rank"])
            if detail.get("taxon_attr"):
                blob["auteur"] = format_auteur(detail["taxon_attr"])
            accepted_name = detail.get("accepted_name")
            if accepted_name and accepted_name != detail.get("taxon_name"):
                blob["nv"] = True

        struct.liens["tpdb"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("tpdb")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        nom = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            nom += " " + data["auteur"]
        return f"{{{{TPDB | {data['id']} | {nom} | consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "tpdb", "https://paleobiodb.org/classic/basicTaxonInfo?taxon_no={id}", "TPDB"
        )


register_module(TpdbModule)
