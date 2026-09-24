"""Animal Diversity Web (ADW) module.

Enrichment only (`can_classify=False`: ADW gives no structured
classification), domain "all". See `adapter.py` for the extraction.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import retrieval_dates
from organon.modules.adw.adapter import AdwAdapter, AdwCitation, Author
from organon.modules.common import format_author, simple_debug_link


def _format_name(author: Author) -> str:
    """Format an author as "Surname, Initials"."""
    return f"{author.nom}, {author.prenom1}{author.prenom2 or ''}"


def _format_citation(citation: AdwCitation) -> str | None:
    """Format the authors like a Wikipedia citation.

    A single author, "X et Y", or "X et al." from 3 authors.
    """
    if citation.premier_auteur is None:
        return None
    first = _format_name(citation.premier_auteur)
    if not citation.autres_auteurs:
        return first
    if len(citation.autres_auteurs) == 1:
        return f"{first} et {_format_name(citation.autres_auteurs[0])}"
    return format_author(f"{first} et al.")


class AdwModule(TaxonomyModule):
    """ADW module."""

    meta = ModuleMeta(id="adw", can_classify=False, can_render_external_link=True, domains="all")

    def __init__(self, adapter: AdwAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or AdwAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the ADW citation of the taxon."""
        if is_classification:
            return None

        slug = struct.taxon.name.replace(" ", "_")
        citation = await self._adapter.fetch(slug)
        if citation is None:
            return None

        data: LinkEntry = {"id": slug}
        authors = _format_citation(citation)
        if authors:
            data["citation"] = authors
        if citation.annee:
            data["date"] = citation.annee

        struct.links["adw"] = data
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{ADW}} template."""
        data = struct.links.get("adw")
        if not data or "id" not in data:
            return None
        cdate = retrieval_dates()
        description = wp_apply_italics(struct.taxon.name, struct.taxon.rank, struct.kingdom)
        adw = f"{{{{ADW | {data['id']} | {description} | consulté le={cdate}"
        if data.get("citation"):
            adw += f" | auteur={data['citation']}"
        if data.get("date"):
            adw += f" | date={data['date']}"
        adw += " }}"
        return adw

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the ADW page."""
        return simple_debug_link(
            struct, "adw", "https://animaldiversity.org/accounts/{id}/", "ADW"
        )


register_module(AdwModule)
