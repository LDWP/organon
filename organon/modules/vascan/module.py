"""Logique métier du module VASCAN (Base de données des plantes vasculaires du Canada) :
enrichissement botanique pur (auteur, noms vernaculaires français, identifiant), domaine
`['végétal']`. Portée volontairement régionale (flore du Canada) — pas une classification
généraliste, et `higherClassification` (chaîne de noms d'ancêtres séparés par `;`) n'est pas
exploitée pour construire `struct.rangs` : l'API ne fournit aucun rang par élément de cette
chaîne (ex. sous-famille et section s'y mélangent sans distinction), ce qui rendrait toute
tentative de reconstruction du rang par position fragile. Comme CITES/NCBI/TelaMétro, ce module
réutilise `struct.taxon.rang` déjà connu plutôt que de deviner.

VASCAN distingue explicitement synonymes et noms acceptés (`taxonomicStatus`) — ce module ne
suit pas la cible acceptée (n'affecte pas la classification), il se contente de marquer le
statut, comme les autres modules d'enrichissement face à un synonyme."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.vascan.adapter import VascanAdapter


class VascanModule(TaxonomyModule):
    meta = ModuleMeta(id="vascan", can_classify=False, can_render_external_link=True, domains=["végétal"])

    def __init__(self, adapter: VascanAdapter | None = None) -> None:
        self._adapter = adapter or VascanAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        matches = await self._adapter.search(struct.taxon.nom)
        if not matches:
            return None
        match = matches[0]

        vascan_link: dict = {
            "id": match["taxonID"],
            "nom": match["canonicalName"],
            "auteur": format_auteur(match.get("scientificNameAuthorship")),
        }
        assertions = match.get("taxonomicAssertions") or []
        if assertions and assertions[0].get("taxonomicStatus") != "accepted":
            vascan_link["synonyme"] = True
        struct.liens["vascan"] = vascan_link

        noms_fr = []
        for entry in match.get("vernacularNames") or []:
            if entry.get("language") == "fr" and entry.get("vernacularName") not in noms_fr:
                noms_fr.append(entry["vernacularName"])
        if noms_fr:
            struct.vernaculaire["VASCAN"] = noms_fr

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("vascan")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        nv = " | nv" if data.get("synonyme") else ""
        return f"{{{{VASCAN | {data['id']} | {cible}{nv} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "vascan", "https://data.canadensys.net/vascan/taxon/{id}", "VASCAN")


register_module(VascanModule)
