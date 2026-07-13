"""Logique métier du module IPNI (International Plant Names Index) : enrichissement botanique
pur (auteur, identifiant), domaine `['végétal']`. Aucune classification — IPNI est un index de
noms publiés (nomenclature), pas un référentiel taxonomique hiérarchique ; comme CITES/NCBI/
TelaMétro, ce module réutilise `struct.taxon.rang` déjà connu plutôt que de traduire un rang
propre (les marqueurs abrégés observés en direct, ex. "spec."/"gen.", ne sont pas assez
documentés pour justifier une table de correspondance dédiée).

`search()` de l'API IPNI mélange dans une même réponse des enregistrements de nom, de
publication et d'auteur ; seul un enregistrement de nom porte un champ `name`, ce qui suffit à
filtrer sans dépendre d'un paramètre de requête IPNI dédié (aucun trouvé de façon fiable en
sondage direct pour restreindre aux seuls noms).

IPNI indexe TOUTE publication d'une combinaison de noms, y compris des homonymes tardifs
n'ayant plus cours : vérifié en direct que "Quercus robur" a trois enregistrements distincts
(Linnaeus 1753, Asso 1779, Pallas 1789) partageant la même chaîne de caractères. Le champ
`inPowo` (`true` uniquement sur l'enregistrement de 1753 dans ce cas) sert de signal fiable
pour préférer la combinaison actuellement reconnue par Plants of the World Online plutôt que de
prendre la première réponse de l'API dans un ordre non garanti."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.ipni.adapter import IpniAdapter


class IpniModule(TaxonomyModule):
    meta = ModuleMeta(id="ipni", can_classify=False, can_render_external_link=True, domains=["végétal"])

    def __init__(self, adapter: IpniAdapter | None = None) -> None:
        self._adapter = adapter or IpniAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        results = await self._adapter.search(struct.taxon.nom)
        exact = [r for r in results if r.get("name") == struct.taxon.nom]
        match = next((r for r in exact if r.get("inPowo")), exact[0] if exact else None)
        if match is None:
            return None

        url = match.get("url") or ""
        ipni_id = url.removeprefix("/n/")
        if not ipni_id:
            return None

        struct.liens["ipni"] = {
            "id": ipni_id,
            "nom": match["name"],
            "auteur": format_auteur(match.get("authors") or match.get("publishingAuthor")),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Le modèle {{IPNI}} met lui-même le paramètre 2 en italique (vérifié sur son
        wikicode : `''{{{2}}}''`, sans condition contrairement à {{GBIF}}) — le nom est donc
        passé tel quel ici, pas pré-italicisé par `wp_met_italiques`. L'auteur va dans le
        paramètre 3, affiché après le nom mais hors de l'italique."""
        data = struct.liens.get("ipni")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        auteur = f" | {data['auteur']}" if data.get("auteur") else ""
        return f"{{{{IPNI | {data['id']} | {data['nom']}{auteur} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "ipni", "https://www.ipni.org/n/{id}", "IPNI")


register_module(IpniModule)
