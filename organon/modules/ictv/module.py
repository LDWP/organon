"""Logique métier du module ICTV : classification de référence pour le domaine `virus` (voir
organon/core/domains.py). Lecture pure du dataset embarqué (adapter.py) — pas de synonymes
(l'ICTV n'en publie pas dans le VMR export) ni d'auteur (l'ICTV ne pratique pas la citation
d'auteur classique des codes zoologique/botanique).

`ICTV_ID` n'existe qu'au rang espèce dans le dataset source (voir scripts/build_ictv_taxonomy.py) :
`render_bioref`/`debug_link` ne produisent donc un lien que pour les taxons de ce rang, `None`
sinon — limite du dataset, pas un oubli."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import simple_debug_link
from organon.modules.ictv.adapter import IctvAdapter
from organon.modules.ictv.ranks import ictv_rang


class IctvModule(TaxonomyModule):
    meta = ModuleMeta(
        id="ictv", can_classify=True, can_render_external_link=True, domains=["virus"]
    )

    def __init__(self, adapter: IctvAdapter | None = None) -> None:
        self._adapter = adapter or IctvAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        record = self._adapter.find(struct.taxon.nom)
        if record is None:
            return None

        rang = ictv_rang(record.rang_colonne)
        ictv_link: dict = {"nom": record.nom, "rang": rang}
        if record.ictv_id:
            ictv_link["id"] = record.ictv_id
        struct.liens["ictv"] = ictv_link

        if not is_classification:
            return struct

        struct.regne = "virus"
        struct.classification = "ICTV"
        struct.classification_taxobox = "ICTV"
        struct.taxon = TaxonInfo(nom=record.nom, rang=rang)

        struct.rangs = [
            RankName(nom=nom, rang=ictv_rang(colonne))
            for colonne, nom in reversed(record.ancestors[:-1])
        ]

        enfants = self._adapter.children_of(record.nom)
        if enfants:
            struct.sous_taxons = SubTaxonList(
                liste=[RankName(nom=nom, rang=ictv_rang(colonne)) for colonne, nom in enfants],
                source="ICTV",
            )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("ictv")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        nom = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        return f"{{{{ICTV | {data['id']} | {nom} |  | consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "ictv", "https://ictv.global/id/{id}", "ICTV")


register_module(IctvModule)
