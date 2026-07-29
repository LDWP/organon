"""Logique métier du module DORIS (doris.ffessm.fr). Module d'enrichissement uniquement
(`can_classify=False`) : le site ne fournit aucune donnée de classification exploitable, juste
un regroupement simplifié par icône ("groupe DORIS") — voir adapter.py pour le détail de la
recherche HTML utilisée en l'absence d'API publique.

Domaine restreint à la faune/flore subaquatique effectivement couverte par le site (animal, algue,
végétal aquatique, protiste — pas de bactérie/champignon/archaea/virus)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.doris.adapter import LEGACY_FICHE_URL, DorisAdapter


class DorisModule(TaxonomyModule):
    meta = ModuleMeta(
        id="doris",
        can_classify=False,
        can_render_external_link=True,
        domains=["animal", "algue", "végétal", "protiste"],
    )

    def __init__(self, adapter: DorisAdapter | None = None) -> None:
        self._adapter = adapter or DorisAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        hit = await self._adapter.search(taxon)
        if hit is None:
            return None
        species_id, nom_commun = hit

        struct.liens["doris"] = {"id": species_id, "nom": taxon, "nom_commun": nom_commun}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("doris")
        if not data:
            return None
        cdate = dates_recupere()
        description = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if struct.taxon.auteur_resolu:
            description += f" {struct.taxon.auteur_resolu}"
        return f"{{{{DORIS | {data['id']} | {description} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("doris")
        if not data:
            return None
        url = f"{LEGACY_FICHE_URL}?fiche_numero={data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>DORIS</a>"


register_module(DorisModule)
