"""Pure parser of the distribution section of a frwiki article.

The section is prose under a variable title, located by keyword in
the title. Only the plants' `{{WGSRPD}}` template is structured and
may appear under any title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from organon.core.taxobox_parser import _parse_args, _templates

_MOTS_TITRE = ("répartition", "distribution")
_TITRE_RE = re.compile(r"^(={2,6})\s*(.*?)\s*=+\s*$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_REF_RE = re.compile(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_WGSRPD_RE = re.compile(r"\{\{\s*WGSRPD\s*\|", re.IGNORECASE)
_STATUTS = {
    "certain": "certain",
    "incertain": "incertain",
    "introduit": "introduit",
    "eteint": "eteint",
    "éteint": "eteint",
}


@dataclass(frozen=True)
class RepartitionView:
    """Parsed distribution of an article.

    `texte` is the located sections stripped of refs, comments and the
    WGSRPD template; empty if `section_identifiee` is False. `wgsrpd`
    is None without a template.
    """

    section_identifiee: bool
    titres: list[str] = field(default_factory=list)
    texte: str = ""
    wgsrpd: dict[str, frozenset[str]] | None = None


def _fin_gabarit(text: str, debut: int) -> int:
    """Return the index just after the template starting at `debut`."""
    depth = 0
    i = debut
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def _extrait_wgsrpd(text: str) -> tuple[str, dict[str, frozenset[str]] | None]:
    """Split out WGSRPD templates; return (text, codes by status)."""
    codes: dict[str, set[str]] | None = None
    morceaux: list[str] = []
    curseur = 0
    for m in _WGSRPD_RE.finditer(text):
        if m.start() < curseur:
            continue
        fin = _fin_gabarit(text, m.start())
        corps = _templates(text[m.start() : fin])[0]
        _, _, named = _parse_args(corps)
        codes = codes if codes is not None else {s: set() for s in _STATUTS.values()}
        for arg, statut in _STATUTS.items():
            codes[statut].update(c.strip() for c in named.get(arg, "").split(",") if c.strip())
        morceaux.append(text[curseur : m.start()])
        curseur = fin
    morceaux.append(text[curseur:])
    figes = {s: frozenset(v) for s, v in codes.items()} if codes is not None else None
    return "".join(morceaux), figes


def parse_repartition(wikitext: str) -> RepartitionView:
    """Parse the distribution sections and WGSRPD codes."""
    texte = _REF_RE.sub("", _COMMENT_RE.sub("", wikitext))
    texte, wgsrpd = _extrait_wgsrpd(texte)

    titres: list[str] = []
    lignes: list[str] = []
    niveau_zone: int | None = None
    for ligne in texte.splitlines():
        titre = _TITRE_RE.match(ligne)
        if titre:
            niveau = len(titre.group(1))
            if niveau_zone is not None and niveau <= niveau_zone:
                niveau_zone = None
            if niveau_zone is None and any(m in titre.group(2).casefold() for m in _MOTS_TITRE):
                niveau_zone = niveau
                titres.append(titre.group(2))
        elif niveau_zone is not None:
            lignes.append(ligne)
    return RepartitionView(bool(titres), titres, "\n".join(lignes).strip(), wgsrpd)
