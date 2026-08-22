"""Logique métier du module EOL (Encyclopedia of Life). Module d'enrichissement uniquement
(`can_classify=False`) : réutilise le rang déjà connu de la classification principale plutôt
que d'en dériver un depuis EOL (pas de champ de rang structuré exploité ici).

L'auteur est extrait de `scientificName` (qui inclut le nom scientifique complet suivi de
l'auteur, ex. "Gadus morhua Linnaeus, 1758") en retranchant le nom déjà connu.

EOL ne contribue pas aux noms vernaculaires français : EOL les recopie de Wikidata (miroir),
ce qui crée des boucles de propagation d'erreurs Wikidata -> EOL -> Wikispecies/Wikipédia FR
(voir ticket #39 sur le wiki Biologie/Organon, cas "Épilobe-mollet" pour Epilobium
parviflorum)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.eol.adapter import EolAdapter


class EolModule(TaxonomyModule):
    meta = ModuleMeta(id="eol", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: EolAdapter | None = None) -> None:
        self._adapter = adapter or EolAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        results = await self._adapter.search(taxon)
        match = next((r for r in results if r.get("title") == taxon), None)
        if match is None:
            return None

        blob: dict = {"id": match["id"], "nom": taxon}

        page = await self._adapter.page(match["id"])
        if page is not None:
            scientific_name = page.get("scientificName") or ""
            if scientific_name.startswith(taxon):
                auteur = scientific_name[len(taxon) :].strip()
                if auteur:
                    blob["auteur"] = format_auteur(auteur)

        struct.liens["eol"] = blob
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("eol")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        return f"{{{{EOL | {data['id']} | {cible} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "eol", "https://eol.org/fr/pages/{id}", "EoL")


register_module(EolModule)
