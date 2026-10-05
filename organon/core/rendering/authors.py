"""Wikification of the main taxon's author citation.

Splits the raw string, links years and known authors from the
tables built by `scripts/build_auteurs_yaml.py`, and wraps unknown
names in `{{auteur}}`. Only `struct.taxon.auteur` goes through
here; synonym, basionym and sub-taxon authors use `format_author`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

import yaml

from organon.core.models import Struct
from organon.core.rendering.support import is_similar
from organon.core.wikidata_authors import normalize_abbreviation

__all__ = [
    "BOTANIST_KINGDOMS",
    "resolve_main_author",
    "unknown_botanist_tokens",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BOTANIST_KINGDOMS = {"végétal", "champignon"}
_PROKARYOTE_KINGDOMS = {"bactérie", "archaea"}
_NO_RESOLUTION_KINGDOMS = {"virus"}

_YEAR_RE = re.compile(r"^(1[3-9]\d\d|20\d\d)$")

# Also matches an already wikified {{et al.}} to avoid resplitting it.
_SPECIAL_WORD_RE = re.compile(
    r"(?<![\w'])(\{\{et al\.\}\}|et al\.|and|emend\.|et non|nom\. nov\.|nom\. cons\.|corrig\.|"
    r"ex\.|ex|in\.|in)(?![\w'])",
    re.IGNORECASE,
)
_SPECIAL_NORMALIZE = {"and": "&", "et al.": "{{et al.}}"}
_PUNCT_RE = re.compile(r"([,&;:()\[\]])")

# Surname particles: the zoologist table omits them ("Haan" → "Willem de
# Haan"), while sources report "De Haan" or "de Haan".
_PARTICLE_RE = re.compile(
    r"^(?:(?:de|der|den|van|von|du|da|di|le|la|del|della|dos|d')\s*)+", re.I
)


@lru_cache(maxsize=3)  # un par fichier d'auteurs (botanistes/procaryotes/zoologistes)
def _load(name: str) -> dict:
    """Load an authors data file; empty if missing."""
    path = DATA_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_botanists() -> dict:
    """Load the botanists table."""
    return _load("auteurs_botanistes.yaml")


def _load_prokaryotes() -> dict:
    """Load the prokaryotes table."""
    return _load("auteurs_procaryotes.yaml")


def _load_zoologists() -> dict:
    """Load the zoologists table."""
    return _load("auteurs_zoologistes.yaml")


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Split into `(type, text)` tokens.

    `sep` for punctuation and keywords, `cur` for text to resolve.
    """
    tokens: list[tuple[str, str]] = []
    parts = _SPECIAL_WORD_RE.split(text)
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 1:  # keyword captured by the _SPECIAL_WORD_RE group
            tokens.append(("sep", _SPECIAL_NORMALIZE.get(part.lower(), part)))
            continue
        for piece in _PUNCT_RE.split(part):
            if piece == "":
                continue
            if _PUNCT_RE.fullmatch(piece):
                tokens.append(("sep", piece))
            else:
                tokens.append(("cur", piece))
    return tokens


def _dates_window(dates: str) -> tuple[int, int] | None:
    """Convert a dates string into a disambiguation window.

    Birth+15 to death+10 if both are known; +-10 years around an
    activity date; birth+15 to birth+70 if only birth; death-70 to
    death+10 if only death. None if unparseable.
    """
    m = re.match(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$", dates)
    if m:
        birth, death = int(m.group(1)), int(m.group(2))
        return birth + 15, death + 10
    m = re.match(r"^\s*(\d{4})\s*-\s*[…\.]*\s*$", dates)
    if m:
        birth = int(m.group(1))
        return birth + 15, birth + 70
    m = re.search(r"fl\.\s*(\d{4})", dates)
    if m:
        activity = int(m.group(1))
        return activity - 10, activity + 10
    m = re.match(r"^\s*\?\s*-\s*(\d{4})\s*$", dates)
    if m:
        death = int(m.group(1))
        return death - 70, death + 10
    return None


def _lookup_normalise(table: dict, token: str) -> dict | None:
    """Look up a token: exact key, then without space after a dot.

    Last, an accent- and case-insensitive match, accepted only if
    unique: homonyms differing by an accent are never guessed.
    """
    entry: dict | None = table.get(token)
    if entry is not None:
        return entry
    spaced: dict | None = table.get(re.sub(r"\.\s+", ".", token))
    if spaced is not None:
        return spaced
    candidates: list[dict] = [value for key, value in table.items() if is_similar(key, token)]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_botanist(token: str, wikidata: Mapping[str, str]) -> tuple[str | None, dict | None]:
    entry = _lookup_normalise(_load_botanists(), token)
    if entry is None:
        qid = wikidata.get(normalize_abbreviation(token))
        if qid is None:
            return None, None
        return f"{{{{Lien|langue=d|trad={qid}|texte={token}|lienfr=non}}}}", None
    if entry.get("conflit"):
        return None, entry
    return f"[[{entry['cible']}|{token}]]", None


def unknown_botanist_tokens(struct: Struct) -> list[str]:
    """Return the author tokens the botanist table cannot resolve.

    Candidates for the Wikidata lookup; empty outside botanists.
    """
    if struct.kingdom not in BOTANIST_KINGDOMS:
        return []
    table = _load_botanists()
    unknown = []
    for kind, text in _tokenize((struct.taxon.author or "").strip()):
        token = text.strip()
        if kind == "cur" and token and not _YEAR_RE.match(token):
            if _lookup_normalise(table, token) is None:
                unknown.append(token)
    return unknown


def _resolve_prokaryote(token: str) -> str | None:
    entry = _lookup_normalise(_load_prokaryotes(), token)
    if entry is None:
        return None
    return f"[[{entry['cible']}|{token}]]"


def _resolve_zoologist(token: str, year: int | None) -> tuple[str | None, list[dict] | None]:
    """Return `(link, homonyms)`.

    `homonyms` is set when several zoologists share the surname and
    the date window cannot decide; nothing is guessed then.
    """
    table = _load_zoologists()
    candidates = table.get(token) or table.get(_PARTICLE_RE.sub("", token))
    if not candidates:
        return None, None
    if len(candidates) == 1:
        return f"[[{candidates[0]['cible']}|{token}]]", None
    if year is None:
        return None, candidates
    matches = []
    for c in candidates:
        window = _dates_window(c.get("dates", ""))
        if window is not None and window[0] <= year <= window[1]:
            matches.append(c)
    if len(matches) == 1:
        return f"[[{matches[0]['cible']}|{token}]]", None
    return None, candidates


def resolve_main_author(
    struct: Struct, wikidata: Mapping[str, str] | None = None
) -> tuple[str, list[str]]:
    """Return `(wikified text, warnings)` for the main author.

    Warnings list botanist conflicts and zoologist homonyms, for the
    caller to add to the API response. `wikidata` maps normalized
    abbreviations to QIDs for botanists missing from the table.
    """
    wikidata = wikidata or {}
    author = (struct.taxon.author or "").strip()
    if not author:
        return "", []

    kingdom = struct.kingdom
    tokens = _tokenize(author)

    year: int | None = None
    resolved_tokens: list[tuple[str, str]] = []  # (type, texte) — type: 'sep' | 'nom' | 'date'
    warnings: list[str] = []

    # First pass: find the year, used to disambiguate zoologists.
    for kind, text in tokens:
        if kind == "cur" and _YEAR_RE.match(text.strip()):
            year = int(text.strip())
            break

    for kind, text in tokens:
        if kind == "sep":
            resolved_tokens.append(("sep", text))
            continue
        stripped = text.strip()
        if not stripped:
            if text:
                resolved_tokens.append(("sep", ""))  # keep an isolated space
            continue
        if _YEAR_RE.match(stripped):
            resolved_tokens.append(("date", f"[[{stripped} en science|{stripped}]]"))
            continue

        resolved: str | None = None
        if kingdom in BOTANIST_KINGDOMS:
            resolved, conflict = _resolve_botanist(stripped, wikidata)
            if conflict is not None:
                warnings.append(
                    f"Auteur « {stripped} » : désaccord entre la liste Wikipédia "
                    f"({conflict['cible']}) et Wikidata ({conflict.get('wikidata_libelle')}) — "
                    "non résolu automatiquement, à trancher manuellement."
                )
        elif kingdom in _PROKARYOTE_KINGDOMS:
            resolved = _resolve_prokaryote(stripped)
        elif kingdom not in _NO_RESOLUTION_KINGDOMS:
            resolved, homonyms = _resolve_zoologist(stripped, year)
            if homonyms is not None:
                targets = ", ".join(
                    f"{c['cible']} ({c['dates']})" if c.get("dates") else c["cible"]
                    for c in homonyms
                )
                warnings.append(
                    f"Auteur « {stripped} » : homonymie entre plusieurs zoologistes "
                    f"({targets}) — non résolu automatiquement, à trancher manuellement."
                )

        if resolved is not None:
            resolved_tokens.append(("nom", resolved))
        else:
            resolved_tokens.append(("nom", f"{{{{auteur|[[{stripped}]]}}}}"))

    text = _render_tokens(resolved_tokens)
    if year is None:
        text += " {{date à préciser}}"
    return text, warnings


_NO_SPACE_BEFORE = {",", ";", ":", ")", "]"}
_NO_SPACE_AFTER = {"(", "["}


def _render_tokens(tokens: list[tuple[str, str]]) -> str:
    """Join resolved tokens with typographic spacing."""
    out = ""
    for kind, text in tokens:
        if not text:
            continue
        if kind == "sep" and text in _NO_SPACE_BEFORE:
            out = out.rstrip() + text + " "
            continue
        if kind == "sep" and text in _NO_SPACE_AFTER:
            out = out.rstrip() + " " + text
            continue
        if out and not out.endswith((" ", "(", "[")):
            out += " "
        out += text
    return re.sub(r" {2,}", " ", out).strip()
