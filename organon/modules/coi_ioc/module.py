"""IOC World Bird List, as used by the COI (dataset 2036)."""

from functools import lru_cache

import yaml

from organon.core.models import LinkEntry, RankName, Struct
from organon.core.registry import ModuleMeta, register_module
from organon.core.rendering.grammar import wp_apply_italics
from organon.core.rendering.support import DATA_DIR, retrieval_dates
from organon.modules.checklistbank import ChecklistBankModule
from organon.modules.col_xr.ranks import col_xr_to_wp_rank


@lru_cache(maxsize=1)
def _slugs_familles() -> dict[str, str]:
    """Family -> slug of worldbirdnames.org/bow/<slug>.

    {{COI}} requires the slug as parameter 1.
    """
    with (DATA_DIR / "ioc_familles.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class CoiIocModule(ChecklistBankModule):
    """IOC World Bird List module, cited as COI."""

    meta = ModuleMeta(
        id="coi_ioc", can_classify=True, can_render_external_link=True, domains=["oiseau"]
    )
    dataset_id = "2036"  # alias "IOC", DOI 10.48580/d4g8, resynced from worldbirdnames.org
    label = "COI"
    debug_label = "COI/IOC"
    site_name = "COI"
    # The classification stops at the infraclass.
    fixed_chain = (
        RankName(name="Aves", rank="classe"),
        RankName(name="Chordata", rank="embranchement"),
    )
    has_synonyms = False  # every record is accepted, the dataset has no synonyms

    def _extra_links(self, current: dict) -> LinkEntry:
        """Return the family of the record."""
        name = current["usage"]["name"]
        family = next(
            (c["name"] for c in current.get("classification", []) if c.get("rank") == "family"),
            None,
        )
        if family is None and col_xr_to_wp_rank(name["rank"]) == "famille":
            family = name["scientificName"]
        return {"family": family}

    def render_bioref(self, struct: Struct) -> str | None:
        """Render a COI template, needing the family."""
        data = struct.links.get(self.meta.id)
        if not data or "id" not in data:
            return None
        family = data.get("family")
        if not family:
            return None
        slug = _slugs_familles().get(family)
        if slug is None:  # Unknown family: any other value yields a dead link.
            return None
        if data.get("rank") == "famille":
            taxon = family
        else:
            taxon = wp_apply_italics(
                data["name"], data.get("rank") or struct.taxon.rank, struct.kingdom
            )
            if author := data.get("author"):
                taxon += " " + author
        return f"{{{{COI | {slug} | {taxon} | consulté le={retrieval_dates()} }}}}"


register_module(CoiIocModule)
