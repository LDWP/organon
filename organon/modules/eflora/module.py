"""Logique métier du module eFlora (eFloras.org). Module d'enrichissement uniquement
(`can_classify=False`), limité au domaine végétal. Une espèce peut avoir une fiche par flore
régionale (Amérique du Nord/Chine/Pakistan) — `render_bioref` renvoie donc une liste, un
`{{EFloras}}` par fiche trouvée, comme `organon.modules.col` pour Catalogue of Life.

Vérifie que le nom affiché sur chaque résultat correspond exactement au taxon demandé avant de
l'accepter (la recherche eFloras.org fait de la correspondance partielle, ex. une recherche par
seul genre renvoie sa propre fiche répétée par flore, mais pourrait aussi renvoyer des taxons
apparentés pour une requête plus ambiguë)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.eflora.adapter import EfloraAdapter


class EfloraModule(TaxonomyModule):
    meta = ModuleMeta(
        id="eflora", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: EfloraAdapter | None = None) -> None:
        self._adapter = adapter or EfloraAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        hits = await self._adapter.search(taxon)
        matches = [(fid, tid) for fid, tid, nom in hits if nom == taxon]
        if not matches:
            return None

        struct.liens["eflora"] = {"nom": taxon, "ids": matches}
        return struct

    def render_bioref(self, struct: Struct) -> list[str] | None:
        data = struct.liens.get("eflora")
        if not data or not data.get("ids"):
            return None
        cdate = dates_recupere()
        return [
            f"{{{{EFloras | {fid} | {tid} | {data['nom']} | consulté le={cdate} }}}}"
            for fid, tid in data["ids"]
        ]

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("eflora")
        if not data or not data.get("ids"):
            return None
        links = [
            f"<a href='http://www.efloras.org/florataxon.aspx?flora_id={fid}&taxon_id={tid}' "
            f"target='_blank' rel='noopener noreferrer'>eFlora ({fid})</a>"
            for fid, tid in data["ids"]
        ]
        return " ".join(links)


register_module(EfloraModule)
