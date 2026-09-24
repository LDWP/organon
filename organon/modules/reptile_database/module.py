"""Reptile Database module.

`can_classify=True`: the species page has a "Higher Taxa" field of which
only the family (first term) and the order (closed vocabulary of 4
orders) are reliably extracted; see `adapter._parse_higher_taxa`.

The site only has a page (`/Genus/species`) for the accepted binomial: a
subspecies trinomial matches nothing and is ignored, so this database
never classifies at subspecies rank. A single-word name (genus or
family) has no page either, only a search form: insufficient to
classify, but enough to confirm the taxon and publish a citation
({{ReptileDB genre}}, {{ReptileDB famille}}) once another module
resolved its rank; see `collect()`.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import retrieval_dates
from organon.modules.common import format_author
from organon.modules.reptile_database.adapter import BASE_URL, ReptileDatabaseAdapter


class ReptileDatabaseModule(TaxonomyModule):
    """Reptile Database module."""

    meta = ModuleMeta(
        id="reptile_database",
        can_classify=True,
        can_render_external_link=True,
        domains=["reptile"],
    )

    def __init__(self, adapter: ReptileDatabaseAdapter | None = None) -> None:
        """Use `adapter` if given, else create one."""
        self._adapter = adapter or ReptileDatabaseAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the taxon from the Reptile Database."""
        taxon = struct.taxon.name
        words = taxon.split()
        if len(words) == 2:
            return await self._collect_species(struct, is_classification, *words)
        # The site has no genus or family page (see adapter.py), only a
        # search form: no classification at those ranks, only a citation
        # once another classification module resolved the rank.
        if len(words) == 1 and not is_classification and struct.taxon.rank in ("genre", "famille"):
            return await self._collect_superior_taxon(struct, struct.taxon.rank, words[0])
        return None

    async def _collect_species(
        self, struct: Struct, is_classification: bool, genus: str, species: str
    ) -> Struct | None:
        """Collect a species from its page."""
        hit = await self._adapter.get_species(genus, species)
        if hit is None:
            return None

        author = format_author(hit.auteur)
        struct.links["reptile_database"] = {
            "rank": "espèce",
            "genus": genus,
            "species": species,
            "author": author,
        }

        if not is_classification:
            return struct
        if hit.famille is None:
            return None

        struct.taxon.rank = "espèce"
        struct.taxon.author = author
        struct.kingdom = "animal"
        struct.classification = "reptiledb"
        struct.classification_taxobox = "Reptile Database"

        ranks = [RankName(name=genus, rank="genre"), RankName(name=hit.famille, rank="famille")]
        if hit.ordre:
            ranks.append(RankName(name=hit.ordre, rank="ordre"))
        struct.ranks = ranks

        return struct

    async def _collect_superior_taxon(self, struct: Struct, rank: str, name: str) -> Struct | None:
        """Confirm a genus or family, for citation only."""
        exists = (
            await self._adapter.genus_exists(name)
            if rank == "genre"
            else await self._adapter.family_exists(name)
        )
        if not exists:
            return None
        struct.links["reptile_database"] = {"rank": rank, "name": name}
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Render the {{ReptileDB ...}} template."""
        data = struct.links.get("reptile_database")
        if not data:
            return None
        cdate = retrieval_dates()
        if data["rank"] == "espèce":
            author = f" | {data['author']}" if data.get("author") else ""
            return (
                f"{{{{ReptileDB espèce | {data['genus']} | {data['species']}{author} "
                f"| consulté le={cdate} }}}}"
            )
        template = "ReptileDB genre" if data["rank"] == "genre" else "ReptileDB famille"
        return f"{{{{{template} | {data['name']} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug link to the Reptile Database."""
        data = struct.links.get("reptile_database")
        if not data:
            return None
        if data["rank"] == "espèce":
            url = f"{BASE_URL}/{data['genus']}/{data['species']}"
        else:
            field = "genus" if data["rank"] == "genre" else "taxon"
            url = (
                f"{BASE_URL}/advanced_search?{field}={data['name']}&exact%5B%5D={field}"
                "&ok=Search&do=AdvancedSearchForm-submit"
            )
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>Reptile Database</a>"


register_module(ReptileDatabaseModule)
