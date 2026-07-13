"""Logique métier du module Tropicos : enrichissement botanique pur (auteur, identifiant),
domaine `['végétal']`. Aucune classification — comme CITES/NCBI/TelaMétro/IPNI/VASCAN, ce
module réutilise `struct.taxon.rang` déjà connu.

`Search/NameLookup` peut renvoyer plusieurs enregistrements partageant exactement le même
`fullName` (homonymes/combinaisons distinctes, ex. *Quercus robur* a au moins deux entrées
réelles : « (Ten.) A. DC. » et « L. ») sans qu'aucun champ ne signale laquelle est actuellement
reconnue — vérifié en direct que `correctNameId`/`correctFullName` restent `null` sur cet
endpoint quel que soit le nom interrogé, y compris pour un synonyme connu. Sans signal fiable
équivalent à l'`inPowo` d'IPNI, ce module se contente de filtrer les résultats dont le
`fullName` correspond exactement au nom recherché, puis prend le premier de ces résultats
exacts — le choix entre plusieurs homonymes exacts reste non résolu, une limite assumée plutôt
que devinée.

`authorString` est utilisé directement (champ déjà prêt à l'emploi, pas de reconstruction par
sous-chaîne nécessaire)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.tropicos.adapter import TropicosAdapter


class TropicosModule(TaxonomyModule):
    meta = ModuleMeta(id="tropicos", can_classify=False, can_render_external_link=True, domains=["végétal"])

    def __init__(self, adapter: TropicosAdapter | None = None) -> None:
        self._adapter = adapter or TropicosAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        results = await self._adapter.search(struct.taxon.nom)
        exact = [r for r in results if r.get("fullName") == struct.taxon.nom]
        if not exact:
            return None
        match = exact[0]

        struct.liens["tropicos"] = {
            "id": match["id"],
            "nom": match["fullName"],
            "auteur": format_auteur(match.get("authorString")),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Le modèle {{Tropicos}} met lui-même le paramètre 2 en italique (vérifié sur son
        wikicode : `''{{{2}}}''`, sans condition, comme {{IPNI}}) — le nom est donc passé tel
        quel, pas pré-italicisé. L'auteur va dans le paramètre 3, hors de l'italique."""
        data = struct.liens.get("tropicos")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        auteur = f" | {data['auteur']}" if data.get("auteur") else ""
        return f"{{{{Tropicos | {data['id']} | {data['nom']}{auteur} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "tropicos", "https://tropicos.org/name/{id}", "Tropicos")


register_module(TropicosModule)
