"""Pure parser of the `{{Taxobox}}` of a frwiki article.

Reads ranks, the `Taxobox taxon` line and the declared
classification source. Nested templates are split by braces, never
line by line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_NAMED_ARG_RE = re.compile(r"^\s*([^\s=\[\]{}|][^=\[\]{}|]*?)\s*=(.*)$", re.DOTALL)


@dataclass(frozen=True)
class TaxoboxRang:
    """A rank line; `nom` is None without a usable latin name."""

    rang: str
    nom: str | None
    eteint: bool


@dataclass(frozen=True)
class TaxoboxTaxon:
    """The `Taxobox taxon` line."""

    regne: str
    rang: str
    nom: str
    eteint: bool


@dataclass(frozen=True)
class TaxoboxUicn:
    """IUCN status: risk code and optional criteria."""

    risque: str
    critere: str | None


@dataclass(frozen=True)
class TaxoboxView:
    """Parsed taxobox."""

    classification: str | None
    taxon: TaxoboxTaxon | None
    rangs: list[TaxoboxRang] = field(default_factory=list)
    uicn: TaxoboxUicn | None = None


def _templates(text: str) -> list[str]:
    """Return the body of each top-level template, in order."""
    found: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            if depth == 0:
                start = i + 2
            depth += 1
            i += 2
        elif pair == "}}" and depth > 0:
            depth -= 1
            if depth == 0:
                found.append(text[start:i])
            i += 2
        else:
            i += 1
    return found


def _split_args(body: str) -> list[str]:
    """Split on `|` outside nested templates and links."""
    parts: list[str] = []
    depth = 0
    current = 0
    i = 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair in ("{{", "[["):
            depth += 1
            i += 2
        elif pair in ("}}", "]]"):
            depth = max(0, depth - 1)
            i += 2
        else:
            if body[i] == "|" and depth == 0:
                parts.append(body[current:i])
                current = i + 1
            i += 1
    parts.append(body[current:])
    return parts


def _clean_name(raw: str) -> str | None:
    """Unwrap links and quotes; None if empty or a template."""
    if "{{" in raw:
        return None
    name = _WIKILINK_RE.sub(r"\1", raw).replace("'", "").strip()
    return name or None


def _parse_args(body: str) -> tuple[str, list[str], dict[str, str]]:
    """Return (name, positional args, named args) of a template body."""
    name, *rest = _split_args(body)
    positional: list[str] = []
    named: dict[str, str] = {}
    for part in rest:
        match = _NAMED_ARG_RE.match(part)
        if match:
            named[match.group(1).strip().casefold()] = match.group(2).strip()
        else:
            positional.append(part.strip())
    return name.strip().casefold(), positional, named


def _eteint(named: dict[str, str]) -> bool:
    """Return True if the `éteint` argument is "oui"."""
    return (named.get("éteint") or named.get("eteint") or "").casefold() == "oui"


def parse_taxobox(wikitext: str) -> TaxoboxView | None:
    """Parse the first taxobox block of `wikitext`.

    None if there is no `{{Taxobox début}}`.
    """
    text = _COMMENT_RE.sub("", wikitext)
    debut = re.search(r"\{\{\s*taxobox début", text, re.IGNORECASE)
    if debut is None:
        return None

    classification: str | None = None
    taxon: TaxoboxTaxon | None = None
    rangs: list[TaxoboxRang] = []
    uicn: TaxoboxUicn | None = None
    for body in _templates(text[debut.start() :]):
        name, positional, named = _parse_args(body)
        if name == "taxobox début":
            classification = named.get("classification") or None
        elif name == "taxobox fin":
            break
        elif name == "taxobox" and len(positional) >= 1:
            nom = _clean_name(positional[-1]) if len(positional) >= 2 else None
            rangs.append(TaxoboxRang(positional[0], nom, _eteint(named)))
        elif name == "taxobox uicn" and positional and positional[0]:
            critere = positional[1] if len(positional) > 1 else ""
            uicn = TaxoboxUicn(positional[0], critere or None)
        elif name == "taxobox taxon" and len(positional) >= 3:
            nom = _clean_name(positional[2])
            if nom:
                taxon = TaxoboxTaxon(positional[0], positional[1], nom, _eteint(named))
    return TaxoboxView(classification, taxon, rangs, uicn)
