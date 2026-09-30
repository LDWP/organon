"""Orchestrator of the `wikimedia` module: the Wikimedia ecosystem.

One subfolder per site rather than a single adapter, so another edition
or wiki is added by a new submodule.

The cross-project links feed the "Autres projets" section, read from
`struct.links["wikimedia"]` (`sections.render_see_also`) with the
sub-keys `commons`, `commons_category`, `wikispecies` and
`frwiktionary`. The `wikipedia` sub-key (portals) is read by
`categorization.link_for_portal`, and `existing_categories` by
`sections.selected_homonym_category`. It never produces a Bioref
citation.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.sections import HOMONYM_CATEGORY_RANKS
from organon.modules.wikimedia.commons.adapter import CommonsAdapter
from organon.modules.wikimedia.species.adapter import SpeciesAdapter
from organon.modules.wikimedia.wikidata.adapter import WikidataSparqlAdapter
from organon.modules.wikimedia.wikipedia.adapter import WikipediaAdapter
from organon.modules.wikimedia.wiktionnaire.adapter import WiktionnaireAdapter

_PORTAL_ANCHOR_RANKS = ("famille", "ordre", "classe")


def _portal_anchor_candidates(struct: Struct) -> list[tuple[str, str]]:
    """Return the (rank, name) pairs whose article may give portals."""
    candidates = []
    if struct.taxon.rank in _PORTAL_ANCHOR_RANKS:
        candidates.append((struct.taxon.rank, struct.taxon.name))
    candidates.extend((r.rank, r.name) for r in struct.ranks if r.rank in _PORTAL_ANCHOR_RANKS)
    return candidates


class WikimediaModule(TaxonomyModule):
    """Wikimedia module."""

    meta = ModuleMeta(
        id="wikimedia", can_classify=False, can_render_external_link=False, domains="all"
    )

    def __init__(
        self,
        wikidata: WikidataSparqlAdapter | None = None,
        commons: CommonsAdapter | None = None,
        species: SpeciesAdapter | None = None,
        wiktionnaire: WiktionnaireAdapter | None = None,
        wikipedia: WikipediaAdapter | None = None,
    ) -> None:
        """Use the given adapters, else create them."""
        self._wikidata = wikidata or WikidataSparqlAdapter()
        self._commons = commons or CommonsAdapter()
        self._species = species or SpeciesAdapter()
        self._wiktionnaire = wiktionnaire or WiktionnaireAdapter()
        self._wikipedia = wikipedia or WikipediaAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        """Collect the sister-project links of the taxon."""
        taxon = struct.taxon.name
        wikimedia: LinkEntry = {}

        qid = await self._wikidata.qid(taxon)
        if qid:
            wikimedia["wikidata"] = {"id": qid}

        if await self._commons.page_exists(taxon):
            wikimedia["commons"] = {"page": taxon}
        if await self._commons.category_exists(taxon):
            wikimedia["commons_category"] = {"page": taxon}
        if await self._species.page_exists(taxon):
            wikimedia["wikispecies"] = {"page": taxon}
        if await self._wiktionnaire.page_exists(taxon):
            wikimedia["frwiktionary"] = {"page": taxon}

        if not is_classification:
            for rank, name in _portal_anchor_candidates(struct):
                portals = await self._wikipedia.portails(name)
                if portals:
                    wikimedia["wikipedia"] = {"portals": portals, "rank": rank, "name": name}
                    break

        if not is_classification:
            existence = await self.existing_categories(struct)
            if existence:
                wikimedia["existing_categories"] = existence

        if not wikimedia:
            return None

        struct.links["wikimedia"] = wikimedia
        return struct

    async def existing_categories(self, struct: Struct) -> dict[str, bool]:
        """Return the frwiki existence of the homonymous category.

        The taxon's own, then its higher ranks, up to the first existing
        one (the following would never be used).
        """
        if struct.taxon.rank not in HOMONYM_CATEGORY_RANKS:
            return {}
        candidates = [struct.taxon.name] + [
            r.name for r in struct.ranks if r.rank in HOMONYM_CATEGORY_RANKS
        ]
        existence: dict[str, bool] = {}
        for name in candidates:
            existence[name] = await self._wikipedia.category_exists(name)
            if existence[name]:
                break
        return existence

    def debug_link(self, struct: Struct) -> str | None:
        """Return the debug links to the sister projects."""
        data = struct.links.get("wikimedia")
        if not data:
            return None
        attrs = "target='_blank' rel='noopener noreferrer'"
        out = []
        if "wikidata" in data:
            qid = data["wikidata"]["id"]
            out.append(f"<a href='https://www.wikidata.org/wiki/{qid}' {attrs}>Wikidata</a>")
        if "wikispecies" in data:
            page = data["wikispecies"]["page"]
            out.append(f"<a href='https://species.wikimedia.org/wiki/{page}' {attrs}>Species</a>")
        if "commons" in data:
            page = data["commons"]["page"]
            out.append(f"<a href='https://commons.wikimedia.org/wiki/{page}' {attrs}>Commons</a>")
        if "commons_category" in data:
            page = data["commons_category"]["page"]
            url = f"https://commons.wikimedia.org/wiki/Category:{page}"
            out.append(f"<a href='{url}' {attrs}>Commons (cat)</a>")
        if "frwiktionary" in data:
            page = data["frwiktionary"]["page"]
            out.append(f"<a href='https://fr.wiktionary.org/wiki/{page}' {attrs}>Wiktionnaire</a>")
        if "wikipedia" in data:
            title = data["wikipedia"]["name"].replace(" ", "_")
            rank = data["wikipedia"]["rank"]
            out.append(
                f"<a href='https://fr.wikipedia.org/wiki/{title}' {attrs}>Portail ({rank} : "
                f"{data['wikipedia']['name']})</a>"
            )
        return " ".join(out) if out else None


register_module(WikimediaModule)
