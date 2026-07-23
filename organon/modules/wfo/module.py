"""Logique métier du module WFO (World Flora Online) : enrichissement botanique pur
(identifiant, auteur), domaine `['végétal']`. Aucune classification malgré la hiérarchie
affichée sur chaque fiche détail (Angiosperms > ordre > famille > genre > ...) : cette
hiérarchie ne descend pas jusqu'au règne/embranchement et mélange des nœuds génériques sans
auteur (ex. « Angiosperms », `wfo-9949999999`) avec des rangs réels — jugée insuffisamment
fiable pour `can_classify=True`, comme déjà tranché côté ancien PHP.

`/search` peut renvoyer plusieurs enregistrements partageant le même nom (homonymes/
combinaisons distinctes, ex. « Quercus robur » a au moins Asso 1779 et L. 1753) : contrairement
à Tropicos, WFO expose un statut taxonomique explicite par résultat (« Accepted Name » /
« Synonym of ... » / « Unchecked »), utilisé ici comme signal de préférence — même principe que
le champ `inPowo` d'IPNI."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.wfo.adapter import WfoAdapter


class WfoModule(TaxonomyModule):
    meta = ModuleMeta(id="wfo", can_classify=False, can_render_external_link=True, domains=["végétal"])

    def __init__(self, adapter: WfoAdapter | None = None) -> None:
        self._adapter = adapter or WfoAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        results = await self._adapter.search(taxon)
        exact = [r for r in results if r["nom"] == taxon]
        if not exact:
            return None
        match = next((r for r in exact if r["statut"] == "Accepted Name"), exact[0])

        struct.liens["wfo"] = {
            "id": match["id"],
            "nom": match["nom"],
            "auteur": format_auteur(match.get("auteur")),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Le modèle {{WFO}} met lui-même le paramètre 2 en italique (`''{{{2}}}''`, vérifié sur
        son wikicode) et reconstruit lui-même le préfixe `wfo-` (`wfo-{{trim|{{{1}}}}}`) : le
        paramètre 1 attendu est donc l'identifiant SANS ce préfixe."""
        data = struct.liens.get("wfo")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        auteur = f" | {data['auteur']}" if data.get("auteur") else ""
        wfo_id = data["id"].removeprefix("wfo-")
        return f"{{{{WFO | {wfo_id} | {data['nom']}{auteur} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "wfo", "https://www.worldfloraonline.org/taxon/{id}", "WFO")


register_module(WfoModule)
