"""Pure parser of the external links of a frwiki article.

Reads `{{Autres projets}}`, `{{catégorie principale}}` and database
lines `* {{Template|id|…}}`, reusing the Taxobox brace-aware split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from organon.core.taxobox_parser import _parse_args, _templates

# Parameter aliases of `Modèle:Autres projets`, mapped to the
# canonical name; a numeric suffix (`species2`) is kept.
_ALIAS_PROJET = {
    "commons": "commons",
    "wikispecies": "wikispecies",
    "species": "wikispecies",
    "wiktionary": "wiktionary",
    "wikt": "wiktionary",
    "wikiversity": "wikiversity",
    "v": "wikiversity",
    "wikibooks": "wikibooks",
    "b": "wikibooks",
    "wikisource": "wikisource",
    "s": "wikisource",
    "wikiquote": "wikiquote",
    "q": "wikiquote",
    "wikinews": "wikinews",
    "n": "wikinews",
    "meta": "meta",
    "m": "meta",
    "outreach": "outreach",
    "wikidata": "wikidata",
    "d": "wikidata",
    "wikivoyage": "wikivoyage",
    "voy": "wikivoyage",
    "incubator": "incubator",
    "incubateur": "incubator",
}
_PARAM_RE = re.compile(r"^([^\d]+?)(\d*)$")
_LIGNE_BASE_RE = re.compile(r"^\*[ \t]*\{\{", re.MULTILINE)
_FIN_ITEM_RE = re.compile(r"\n(?:[*=]|[ \t]*\n)")


@dataclass(frozen=True)
class CategoriePrincipale:
    """Main category; `titre` is None without argument."""

    titre: str | None


def _nom_modele(name: str) -> str:
    """Normalize underscores in a template name."""
    return name.replace("_", " ")


def _projet(param: str) -> str | None:
    """Return the canonical project name of a parameter, or None."""
    match = _PARAM_RE.match(param)
    if not match:
        return None
    base = _ALIAS_PROJET.get(match.group(1).strip())
    return f"{base}{match.group(2)}" if base else None


def parse_autres_projets(wikitext: str) -> dict[str, str]:
    """Return {normalized project: target} from `{{Autres projets}}`.

    Unknown parameters and empty values are ignored. The first
    positional argument is `commons` unless `commons=` is explicit.
    """
    projets: dict[str, str] = {}
    for body in _templates(wikitext):
        name, positional, named = _parse_args(body)
        if _nom_modele(name) != "autres projets":
            continue
        found: dict[str, str] = {}
        if positional and positional[0]:
            found["commons"] = positional[0]
        for param, value in named.items():
            projet = _projet(param)
            if projet and value:
                found[projet] = value
        if "commons" in named and not named["commons"]:
            found.pop("commons", None)
        for projet, cible in found.items():
            projets.setdefault(projet, cible)
    return projets


def parse_bases(wikitext: str) -> list[tuple[str, str]]:
    """Return (casefolded template, first argument) per `* {{…}}` line.

    The argument is empty if the template has none.
    """
    bases: list[tuple[str, str]] = []
    for match in _LIGNE_BASE_RE.finditer(wikitext):
        start = match.end() - 2
        fin = _FIN_ITEM_RE.search(wikitext, start)
        chunk = wikitext[start : fin.start() if fin else len(wikitext)]
        templates = _templates(chunk)
        if not templates:
            continue
        name, positional, _named = _parse_args(templates[0])
        bases.append((_nom_modele(name), positional[0] if positional else ""))
    return bases


def parse_categorie_principale(wikitext: str) -> CategoriePrincipale | None:
    """Parse `{{catégorie principale}}`; None if absent."""
    for body in _templates(wikitext):
        name, positional, _named = _parse_args(body)
        if _nom_modele(name) == "catégorie principale":
            return CategoriePrincipale(positional[0] if positional and positional[0] else None)
    return None
