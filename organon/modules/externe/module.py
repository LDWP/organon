"""Logique métier du module `externe` : liens transversaux vers Wikidata, Commons (article et
catégorie), Wikispecies et le Wiktionnaire francophone. Ne produit jamais de citation Bioref —
ces liens alimentent la section « Autres projets » du rendu, câblée pour lire
`struct.liens["externe"]` (`organon.core.rendering.sections.render_voir_aussi`), avec les
sous-clés `commons`/`ccommons`/`species`/`frwiktionary` exactement telles qu'attendues
là-bas."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.externe.adapter import ExterneAdapter


class ExterneModule(TaxonomyModule):
    meta = ModuleMeta(id="externe", can_classify=False, can_render_external_link=False, domains="all")

    def __init__(self, adapter: ExterneAdapter | None = None) -> None:
        self._adapter = adapter or ExterneAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        taxon = struct.taxon.nom
        adapter = self._adapter

        externe: dict = {}

        qid = await adapter.wikidata_qid(taxon)
        if qid:
            externe["wikidata"] = {"id": qid}

        if await adapter.commons_page_exists(taxon):
            externe["commons"] = {"page": taxon}
        if await adapter.commons_category_exists(taxon):
            externe["ccommons"] = {"page": taxon}
        if await adapter.species_page_exists(taxon):
            externe["species"] = {"page": taxon}
        if await adapter.frwiktionary_page_exists(taxon):
            externe["frwiktionary"] = {"page": taxon}

        if not externe:
            return None

        struct.liens["externe"] = externe
        return struct

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("externe")
        if not data:
            return None
        attrs = "target='_blank' rel='noopener noreferrer'"
        out = []
        if "wikidata" in data:
            out.append(f"<a href='https://www.wikidata.org/wiki/{data['wikidata']['id']}' {attrs}>Wikidata</a>")
        if "species" in data:
            out.append(f"<a href='https://species.wikimedia.org/wiki/{data['species']['page']}' {attrs}>Species</a>")
        if "commons" in data:
            out.append(
                f"<a href='https://commons.wikimedia.org/wiki/{data['commons']['page']}' {attrs}>Commons (page)</a>"
            )
        if "ccommons" in data:
            out.append(
                f"<a href='https://commons.wikimedia.org/wiki/Category:{data['ccommons']['page']}' {attrs}>"
                "Commons (cat)</a>"
            )
        if "frwiktionary" in data:
            out.append(
                f"<a href='https://fr.wiktionary.org/wiki/{data['frwiktionary']['page']}' {attrs}>Wiktionnaire</a>"
            )
        return " ".join(out) if out else None


register_module(ExterneModule)
