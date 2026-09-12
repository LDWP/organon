"""Logique métier du module WFO (World Flora Online) : classification (domaine `['végétal']`),
identifiant, auteur — limitée aux noms de rôle `accepted` (voir `adapter.py` pour l'API GraphQL
utilisée). Chaque ancêtre de la chaîne de classification porte son rang exact (enum GraphQL
`Rank`, voir `organon.modules.wfo.ranks`) — y compris « Angiosperms » (`wfo-9949999999`),
accepté au rang phylum côté WFO bien que sans terminaison latine standard ni auteur.

`taxonNameSuggestion` (recherche, voir `adapter.py`) peut renvoyer plusieurs enregistrements
partageant le même nom (homonymes/combinaisons distinctes, ex. « Quercus robur » a au moins
Asso 1779 et L. 1753) : WFO expose un rôle taxonomique explicite par résultat (`accepted` /
`synonym` / `unplaced`), utilisé ici comme signal de préférence — même principe que le champ
`inPowo` d'IPNI. Pas de suivi de synonyme (contrairement à POWO/GBIF/ITIS) : un enregistrement
non `accepted` reste utilisable en enrichissement mais ne produit aucune classification, plutôt
que de relancer la collecte sur un nom accepté potentiellement absent."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.wfo.adapter import WfoAdapter
from organon.modules.wfo.ranks import wfo_cherche_rang


class WfoModule(TaxonomyModule):
    meta = ModuleMeta(
        id="wfo", can_classify=True, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: WfoAdapter | None = None) -> None:
        self._adapter = adapter or WfoAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        taxon = struct.taxon.nom
        results = await self._adapter.search(taxon)
        exact = [r for r in results if r["nom"] == taxon]
        if not exact:
            return None
        match = next((r for r in exact if r["statut"] == "accepted"), exact[0])

        struct.liens["wfo"] = {
            "id": match["id"],
            "nom": match["nom"],
            "auteur": format_auteur(match.get("auteur")),
        }

        if not is_classification:
            return struct
        if match["statut"] != "accepted":
            return None

        ancestors = await self._adapter.ancestors(match["id"])
        rangs = [
            RankName(nom=a["nom"], auteur=format_auteur(a["auteur"]), rang=rang)
            for a in ancestors
            if (rang := wfo_cherche_rang(a["rang_brut"])) is not None and rang != "règne"
        ]

        struct.taxon.rang = wfo_cherche_rang(match.get("rang_brut"))
        struct.taxon.auteur = format_auteur(match.get("auteur"))
        struct.regne = "végétal"
        struct.classification = "WFO"
        struct.classification_taxobox = "WFO"
        struct.rangs = rangs
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
        return simple_debug_link(
            struct, "wfo", "https://www.worldfloraonline.org/taxon/{id}", "WFO"
        )


register_module(WfoModule)
