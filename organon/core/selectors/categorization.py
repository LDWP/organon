"""Compute the stub and the portals and categories.

Uses the safe rule engine of `organon.core.selectors.engine`, no
`eval()`. Pure derivation from a resolved `Struct`, with no
third-party call, so it lives here and not in `organon.modules`.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import LinkEntry, Struct
from organon.core.rendering.grammar import CATEGORY_BY_KINGDOM
from organon.core.rendering.sections import selected_homonym_category
from organon.core.selectors.engine import evaluate_ruleset

_PORTAL_BY_KINGDOM: dict[str, str] = {
    "animal": "zoologie",
    "végétal": "botanique",
    "champignon": "mycologie",
    "algue": "phycologie",
    "reptile": "herpétologie",
    "amphibien": "herpétologie",
    "virus": "virologie",
    "archaea": "microbiologie",
    "bactérie": "microbiologie",
    "protiste": "microbiologie",
}
_DEFAULT_PORTAL = "biologie"


def link_for_category(struct: Struct, options: GenerateOptions) -> list[str] | None:
    """Return the categories from the rules, else the kingdom table."""
    if options.selectors:
        ret = evaluate_ruleset("categories", struct)
        if ret is not None:
            return ret
    if struct.kingdom in CATEGORY_BY_KINGDOM and CATEGORY_BY_KINGDOM[struct.kingdom]:
        return [CATEGORY_BY_KINGDOM[struct.kingdom]]
    return None


def link_for_portal(
    default_portal: str, struct: Struct, options: GenerateOptions
) -> list[str] | None:
    """Return the portals from the rules, else the wikimedia ones."""
    if options.selectors:
        ret = evaluate_ruleset("portails", struct)
        if ret is not None:
            return ret
        dynamic = struct.links.get("wikimedia", {}).get("wikipedia", {}).get("portals")
        if dynamic:
            return dynamic
    return None


def compute_footer_links(struct: Struct, options: GenerateOptions) -> LinkEntry:
    """Compute the content of `struct.liens['fin']`.

    Returns portals and categories without assigning them, so the
    caller owns the mutation of `Struct`.
    """
    default_portal = _PORTAL_BY_KINGDOM.get(struct.kingdom, _DEFAULT_PORTAL)
    portals = link_for_portal(default_portal, struct, options) or [default_portal]

    categories = [r.name for r in struct.ranks if r.rank == "famille"]
    categories.extend(link_for_category(struct, options) or [])

    homonym = selected_homonym_category(struct)
    if homonym == struct.taxon.name:
        categories.append(f"{homonym}|{options.homonym_category_key}")
    elif homonym:
        categories.append(homonym)
    categories.sort()

    return {"portals": portals, "categories": categories}
