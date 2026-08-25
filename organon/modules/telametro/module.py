"""Logique métier du module TelaMétro (Tela Botanica, référentiel BDTFX — flore de France
métropolitaine). Module d'enrichissement uniquement (`can_classify=False`), limité au domaine
végétal. Réutilise nom/rang déjà connus de la classification principale (BDTFX n'expose pas de
rang traduisible directement vers le vocabulaire Wikipédia dans cette recherche).

Les noms vernaculaires viennent d'un second appel (`noms_communs_fr`, scraping de l'onglet
Ethnobotanique) plutôt que du `common_name` renvoyé par la recherche Algolia — voir
`TelametroAdapter` pour pourquoi ce dernier est insuffisant. Alimentent `struct.autres_noms`
(groupés par statut BDTFX), pas `struct.vernaculaire` : contrairement aux autres sources de
noms vernaculaires, la BDTFX qualifie elle-même chaque nom d'un statut explicite, information
qu'on ne veut pas perdre en la fondant dans la liste plate `vernaculaire`."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.telametro.adapter import TelametroAdapter


class TelametroModule(TaxonomyModule):
    meta = ModuleMeta(
        id="telametro", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: TelametroAdapter | None = None) -> None:
        self._adapter = adapter or TelametroAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        taxon = struct.taxon.nom
        hits = await self._adapter.search(taxon)

        match = None
        for hit in hits:
            bdtfx = hit.get("bdtfx")
            if not bdtfx:
                continue
            if (bdtfx.get("scientific_name") or "").strip() == taxon:
                match = bdtfx
                break
        if match is None:
            return None

        auteur = match.get("author") or ""
        year = match.get("year")
        if year:
            auteur = f"{auteur} {year}".strip()

        blob: dict = {"id": match["nomenclatural_number"], "nom": taxon}
        if auteur:
            blob["auteur"] = format_auteur(auteur)
        struct.liens["telametro"] = blob

        autres_noms = await self._adapter.noms_communs_fr(match["nomenclatural_number"])
        if autres_noms:
            struct.autres_noms["Tela-métro"] = autres_noms

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("telametro")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        texte = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            texte += " " + data["auteur"]
        return f"{{{{Tela-métro | {data['id']} | {texte} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct,
            "telametro",
            "https://www.tela-botanica.org/eflore/?referentiel=bdtfx&module=fiche&action=fiche"
            "&num_nom={id}&onglet=synthese",
            "TelaMétro",
        )


register_module(TelametroModule)
