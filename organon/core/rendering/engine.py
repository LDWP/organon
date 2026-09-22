"""Rendering orchestrator: assembles the article sections in order."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.rendering import sections
from organon.core.rendering.grammar import STUB_BY_KINGDOM
from organon.core.selectors.engine import evaluate_ruleset

__all__ = [
    "render",
    "render_references_items_block",
    "render_subtaxa_block",
    "render_taxobox_block",
    "wp_stub",
]


def wp_stub(struct: Struct, options: GenerateOptions) -> list[str]:
    """Compute the stub templates, rules first, then the kingdom table.

    Imported lazily to avoid a cycle with selectors.
    """
    if options.selectors:
        ret = evaluate_ruleset("ebauches", struct)
        if ret is not None:
            return ret
    if struct.kingdom in STUB_BY_KINGDOM:
        return [STUB_BY_KINGDOM[struct.kingdom]]
    return []


def render_taxobox_block(struct: Struct, options: GenerateOptions) -> str:
    """Render the `{{ébauche}}` to `{{Taxobox fin}}` block alone.

    Lets the API swap this block without regenerating the article.
    """
    stub = wp_stub(struct, options)
    return sections.render_taxobox(struct, options, stub)


def render_subtaxa_block(struct: Struct, options: GenerateOptions) -> str:
    """Render the sub-taxa section alone.

    Lets the API swap this section without regenerating the article.
    """
    return sections.render_lower_taxa(struct, options)


def render_references_items_block(struct: Struct) -> list[tuple[str, str]]:
    """Render taxonomic references as (module_id, wikitext) pairs.

    Not used by `render()`; exposed separately for the frontend.
    """
    return sections.render_references_items(struct)


def render(struct: Struct, options: GenerateOptions, ext_only: bool = False) -> str:
    """Assemble the full article.

    `ext_only` renders only the "Voir aussi" and external links area.
    """
    ret = ""

    if not ext_only:
        ret += render_taxobox_block(struct, options)
        ret += sections.render_intro(struct)
        ret += sections.render_description(struct, options)
        ret += sections.render_distribution(struct, options)
        ret += render_subtaxa_block(struct, options)
        ret += sections.render_systematics(struct, options)
        ret += sections.render_etymology(struct, options)
        ret += sections.render_original(struct, options)

    ret += sections.render_see_also(struct, options)

    if not ext_only:
        ret += sections.render_footer(struct, notes='group="note"' in ret)

    while "\n\n\n" in ret:
        ret = ret.replace("\n\n\n", "\n\n")

    return ret.rstrip("\n")
