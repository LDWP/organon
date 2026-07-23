"""Logique métier du module Animal Diversity Web (ADW, animaldiversity.org). Module
d'enrichissement uniquement (`can_classify=False` — ADW ne fournit aucune classification
structurée, comme dans le PHP d'origine), domaine "tous". Voir le docstring de `adapter.py`
pour le détail de l'extraction et les écarts constatés en direct par rapport au PHP."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.adw.adapter import AdwAdapter, AdwCitation, Author
from organon.modules.common import format_auteur, simple_debug_link


def _format_nom(auteur: Author) -> str:
    return f"{auteur.nom}, {auteur.prenom1}{auteur.prenom2 or ''}"


def _format_citation(citation: AdwCitation) -> str | None:
    """Formate premier_auteur/autres_auteurs façon citation Wikipédia : auteur seul, "X et Y",
    ou "X et al." à partir de 3 auteurs — comme le PHP d'origine."""
    if citation.premier_auteur is None:
        return None
    premier = _format_nom(citation.premier_auteur)
    if not citation.autres_auteurs:
        return premier
    if len(citation.autres_auteurs) == 1:
        return f"{premier} et {_format_nom(citation.autres_auteurs[0])}"
    return format_auteur(f"{premier} et al.")


class AdwModule(TaxonomyModule):
    meta = ModuleMeta(id="adw", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: AdwAdapter | None = None) -> None:
        self._adapter = adapter or AdwAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None

        slug = struct.taxon.nom.replace(" ", "_")
        citation = await self._adapter.fetch(slug)
        if citation is None:
            return None

        data: dict = {"id": slug}
        auteurs = _format_citation(citation)
        if auteurs:
            data["citation"] = auteurs
        if citation.annee:
            data["date"] = citation.annee

        struct.liens["adw"] = data
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("adw")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        description = wp_met_italiques(struct.taxon.nom, struct.taxon.rang, struct.regne)
        adw = f"{{{{ADW | {data['id']} | {description} | consulté le={cdate}"
        if data.get("citation"):
            adw += f" | auteur={data['citation']}"
        if data.get("date"):
            adw += f" | date={data['date']}"
        adw += " }}"
        return adw

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "adw", "https://animaldiversity.org/accounts/{id}/", "ADW"
        )


register_module(AdwModule)
