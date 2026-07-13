"""Logique métier du module CoL (Catalogue of Life) : enrichissement uniquement
(`can_classify=False` — la classification interne récupérée n'alimente que l'option
`juste-ext`, jamais `struct.rangs`) — peut renvoyer PLUSIEURS fiches pour un même taxon demandé
(cas d'homonymie/synonymie non résolue côté CoL : plusieurs usages distincts partagent le même
nom scientifique), d'où le retour `list[str]` de `render_bioref` (voir le type
`str | list[str] | None` de `organon.core.registry.TaxonomyModule`).

Les identifiants ChecklistBank sont des chaînes alphanumériques d'une vingtaine de caractères
(ex. `JFoARuPAMKtcBxRTJf4-D2`) ; aucun filtre de longueur n'est appliqué sur `id` avant rendu."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.domains import KINGDOM_MAP
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.col.adapter import ColAdapter
from organon.modules.col.ranks import col_cherche_rang
from organon.modules.common import format_auteur


def _bundle_from_name(usage_id: str, name: dict, syn: bool = False) -> dict:
    bundle: dict = {"id": usage_id, "nom": name["scientificName"]}
    auteur = name.get("authorship")
    if auteur:
        bundle["auteur"] = format_auteur(auteur)
    rang = name.get("rank")
    if rang:
        bundle["rang"] = col_cherche_rang(rang)
    if syn:
        bundle["syn"] = True
    return bundle


def _col_regne(classification: list[dict]) -> str | None:
    for el in classification:
        regne = KINGDOM_MAP.get(el.get("name", ""))
        if regne:
            return regne
    return None


class ColModule(TaxonomyModule):
    meta = ModuleMeta(id="col", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: ColAdapter | None = None) -> None:
        self._adapter = adapter or ColAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        res = await self._adapter.search(taxon)
        if res is None:
            return None
        results = res.get("result")
        if not results:
            return None

        bundles: list[dict] = []
        classification: list[dict] | None = None

        for r in results:
            usage = r["usage"]
            if usage.get("status") == "accepted" and usage["name"]["scientificName"] == taxon:
                bundles = [_bundle_from_name(r["id"], usage["name"])]
                classification = r.get("classification")
                break

        if not bundles:
            for r in results:
                usage = r["usage"]
                accepted = usage.get("accepted")
                if (
                    usage["name"]["scientificName"] == taxon
                    and accepted
                    and accepted.get("status") == "accepted"
                ):
                    bundles.append(_bundle_from_name(accepted["id"], accepted["name"], syn=True))
                    classification = r.get("classification")

        if not bundles and options.inclure_invalides:
            for r in results:
                usage = r["usage"]
                if usage["name"]["scientificName"] == taxon:
                    bundles = [_bundle_from_name(r["id"], usage["name"])]
                    classification = r.get("classification")
                    break

        if options.juste_ext and classification:
            regne = _col_regne(classification)
            if regne:
                struct.regne = regne

        if not bundles:
            return None

        struct.liens["col"] = {"bundles": bundles}
        return struct

    def render_bioref(self, struct: Struct) -> list[str] | None:
        data = struct.liens.get("col")
        if not data or not data.get("bundles"):
            return None
        cdate = dates_recupere()
        out: list[str] = []
        for bundle in data["bundles"]:
            cible = wp_met_italiques(bundle["nom"], bundle.get("rang") or struct.taxon.rang, struct.regne)
            if bundle.get("auteur"):
                cible += " " + bundle["auteur"]
            if bundle.get("syn"):
                cible += " <small>(synonymie)</small>"
            out.append(f"{{{{CatalogueofLife | {bundle['id']} | {cible} | consulté le={cdate} }}}}")
        return out or None

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("col")
        if not data or not data.get("bundles"):
            return None
        links = [
            f"<a href='https://www.catalogueoflife.org/data/taxon/{b['id']}' target='_blank' "
            f"rel='noopener noreferrer'>CoL</a>"
            for b in data["bundles"]
        ]
        return " ".join(links) if links else None


register_module(ColModule)
