"""Logique métier du module MSW (Mammal Species of the World, 3e éd., Bucknell/ASM).
Enrichissement uniquement (`can_classify=False`), limité au domaine mammifère. `search.asp`
faisant de la recherche plein texte, chaque résultat est revérifié contre le nom exact demandé
avant d'être accepté (voir `organon.modules.eflora`, même défaut côté source). Contrairement à
eflora, un nom donné ne correspond en général qu'à une seule fiche MSW (pas de fragmentation par
flore régionale) : `render_bioref` renvoie donc une chaîne unique."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur
from organon.modules.msw.adapter import MswAdapter


class MswModule(TaxonomyModule):
    meta = ModuleMeta(
        id="msw", can_classify=False, can_render_external_link=True, domains=["mammifère"]
    )

    def __init__(self, adapter: MswAdapter | None = None) -> None:
        self._adapter = adapter or MswAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        hits = await self._adapter.search(taxon)
        matches = [id_ for id_, nom in hits if nom == taxon]
        if not matches:
            return None

        msw_id = matches[0]
        auteur = format_auteur(await self._adapter.author(msw_id))
        struct.liens["msw"] = {"nom": taxon, "id": msw_id, "auteur": auteur}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("msw")
        if not data:
            return None
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        cdate = dates_recupere()
        return f"{{{{MSW | {data['id']} | {cible} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("msw")
        if not data:
            return None
        return (
            f"<a href='https://www.departments.bucknell.edu/biology/resources/msw3/browse.asp"
            f"?s=y&id={data['id']}' target='_blank' rel='noopener noreferrer'>MSW</a>"
        )


register_module(MswModule)
