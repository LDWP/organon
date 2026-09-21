"""Logique métier du module GTDB (Genome Taxonomy Database) : enrichissement pur (identifiant,
lien vers la fiche source) via ChecklistBank dataset 2214 — voir `adapter.py`. Domaine restreint
à `["bactérie", "archaea", "procaryote"]`, comme `organon.modules.lpsn.module`.

`can_classify=False` délibéré, contrairement à Bryonames/GRIN (même plateforme ChecklistBank) :
GTDB attribue des noms d'espèces provisoires suffixés (ex. "Escherichia hormaechei_A", vérifié en
direct) aux génomes non cultivés ou aux groupes cryptiques distingués par ANI sans nom latin
publié — ce ne sont pas des noms disponibles au sens du Code international de nomenclature des
procaryotes. La documentation du dataset le confirme explicitement (« LPSN is used as the primary
nomenclatural reference for establishing naming priorities... genome assembly identifiers are now
used to create placeholder names for uncultured taxa »). LPSN reste donc la seule source de
classification pour ce domaine (voir `organon.modules.lpsn.module` et la règle de non-correction
inter-source) ; GTDB n'apporte ici qu'un lien vers le placement phylogénomique du taxon, jamais un
nom ou une hiérarchie qui remplacerait ceux de LPSN.

Comme le dataset ne connaît que des enregistrements "accepted" (vérifié en direct : aucun statut
"synonym" observé, la taxonomie GTDB n'ayant pas de notion de synonymie), aucune logique de suivi
de synonyme n'est nécessaire ici, contrairement à Bryonames/GRIN."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur
from organon.modules.gtdb.adapter import GtdbAdapter
from organon.modules.gtdb.ranks import gtdb_cherche_rang


class GtdbModule(TaxonomyModule):
    meta = ModuleMeta(
        id="gtdb",
        can_classify=False,
        can_render_external_link=True,
        domains=["bactérie", "archaea", "procaryote"],
    )

    def __init__(self, adapter: GtdbAdapter | None = None) -> None:
        self._adapter = adapter or GtdbAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        candidats = await self._adapter.search(struct.taxon.nom)
        exact = [r for r in candidats if r["usage"]["name"]["scientificName"] == struct.taxon.nom]
        cur = exact[0] if exact else None
        if cur is None:
            return None

        name = cur["usage"]["name"]
        struct.liens["gtdb"] = {
            "id": cur["id"],
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": gtdb_cherche_rang(name["rank"]),
            "link": name.get("link"),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("gtdb")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        url = data.get("link") or f"https://www.checklistbank.org/dataset/2214/taxon/{data['id']}"
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=GTDB | consulté le={cdate} }}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("gtdb")
        if not data or "id" not in data:
            return None
        url = data.get("link") or f"https://www.checklistbank.org/dataset/2214/taxon/{data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>GTDB</a>"


register_module(GtdbModule)
