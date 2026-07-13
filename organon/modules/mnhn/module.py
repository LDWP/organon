"""Logique métier du module MNHN (science.mnhn.fr). Module d'enrichissement uniquement
(`can_classify=False`), limité aux rangs espèce et genre — le site ne propose de fiche dédiée
que pour ces deux niveaux.

Bug corrigé plutôt que reproduit (intention non ambiguë, vérifié en direct) : l'URL était
construite en remplaçant l'espace par `/_` (ex. `species/gadus/_morhua`), qui renvoie
systématiquement 404 sur le site actuel — le séparateur correct est un simple `/`
(`species/gadus/morhua`, confirmé fonctionnel). Sans cette correction, le module ne pouvait
jamais trouver la moindre espèce."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.mnhn.adapter import MnhnAdapter

_RANK_PATH = {"espèce": "species", "genre": "genus"}


class MnhnModule(TaxonomyModule):
    meta = ModuleMeta(id="mnhn", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: MnhnAdapter | None = None) -> None:
        self._adapter = adapter or MnhnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        rang = struct.taxon.rang
        segment = _RANK_PATH.get(rang or "")
        if segment is None:
            return None

        slug = struct.taxon.nom.lower().replace(" ", "/")
        path = f"{segment}/{slug}"

        if not await self._adapter.exists(path):
            return None

        struct.liens["mnhn"] = {"id": slug, "rang": rang, "url": f"https://science.mnhn.fr/taxon/{path}"}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("mnhn")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        description = wp_met_italiques(struct.taxon.nom, data.get("rang") or struct.taxon.rang, struct.regne)
        return f"{{{{MNHN | {data['rang']} | {data['id']} | {description} | consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("mnhn")
        if not data or "url" not in data:
            return None
        return f"<a href='{data['url']}' target='_blank' rel='noopener noreferrer'>MNHN</a>"


register_module(MnhnModule)
