"""Small rendering helpers.

Current French date, columns, vernacular names, "et al.", country
tables and homonym disambiguation. `format_author` is the simple
author format; the full one is in `organon.core.rendering.authors`.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from organon.core.config import GenerateOptions

__all__ = [
    "DATA_DIR",
    "add_if_needed",
    "condition_names",
    "country_data_by_code",
    "find_homonym",
    "format_author",
    "is_similar",
    "replace_et_al",
    "retrieval_dates",
    "use_columns",
    "wgsrpd_continents_for_codes",
    "wgsrpd_data_by_code",
    "wrap_in_columns",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_FRENCH_MONTHS = {
    1: "janvier",
    2: "février",
    3: "mars",
    4: "avril",
    5: "mai",
    6: "juin",
    7: "juillet",
    8: "août",
    9: "septembre",
    10: "octobre",
    11: "novembre",
    12: "décembre",
}


def retrieval_dates(today: datetime.date | None = None) -> str:
    """Return the date in French, e.g. "9 juillet 2026"."""
    day = today or datetime.date.today()
    return f"{day.day} {_FRENCH_MONTHS[day.month]} {day.year}"


_ET_AL_RE = re.compile(r"([^{])et al[.]")


def replace_et_al(text: str) -> str:
    """Replace "et al." with {{et al.}} unless already done."""
    if "{{et al.}}" in text:
        return text
    return _ET_AL_RE.sub(r"\1{{et al.}}", text)


def format_author(author: str | None) -> str:
    """Return an author citation with "et al." templated."""
    if not author:
        return ""
    return replace_et_al(author)


@lru_cache(maxsize=1)
def _load_homonyms() -> dict[str, dict[str, str]]:
    """Load the homonym table."""
    with (DATA_DIR / "homonymes.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def find_homonym(name: str, kingdom: str) -> tuple[bool, str | None]:
    """Look up `nom` in the homonym table.

    Try the kingdom, then the generic `*` key, then `hom` (a
    disambiguation page to fix by hand, returned as
    `(True, target)`). Return `(False, None)` if absent.
    """
    entry = _load_homonyms().get(name)
    if entry is None:
        return False, None
    if kingdom in entry:
        return False, entry[kingdom]
    if kingdom != "*" and "*" in entry:
        return False, entry["*"]
    if "hom" in entry:
        return True, entry["hom"]
    return False, None


def use_columns(count: int, options: GenerateOptions) -> bool:
    """Return True if a list of `count` items goes in columns.

    `column_threshold` -1 means never, 0 always.
    """
    if options.column_threshold == -1:
        return False
    if options.column_threshold == 0:
        return True
    return count > options.column_threshold


def wrap_in_columns(content: str) -> str:
    """Wrap `contenu` in a {{colonnes}} template."""
    return "{{colonnes|taille=25|1=\n" + content + "}}\n"


def _without_accents(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c))


def _accent_count(word: str) -> int:
    """Count diacritics in `mot`.

    Breaks ties between spellings differing only by accents.
    """
    return sum(1 for c in unicodedata.normalize("NFD", word) if unicodedata.combining(c))


def is_similar(word_1: str, word_2: str) -> bool:
    """Compare two words ignoring case, hyphens and accents."""

    def normalise(m: str) -> str:
        return _without_accents(m.lower().replace("-", " "))

    return normalise(word_1) == normalise(word_2)


def _split_name(name: str) -> list[str]:
    """Split a name on inner commas, as EOL concatenates names."""
    return [n.strip() for n in name.split(",") if n.strip()]


def _rename_key(items: dict[str, list[str]], old: str, new: str) -> None:
    """Rename a key in place, keeping its position."""
    rebuilt = {new if k == old else k: v for k, v in items.items()}
    items.clear()
    items.update(rebuilt)


def add_if_needed(items: dict[str, list[str]], element: str, src: str) -> None:
    """Add `el` with source `src`, merging similar entries.

    `el` is split on inner commas. Of two similar spellings the more
    accented is kept for display; sources accumulate.
    """
    for name in _split_name(element):
        _add_unique_name(items, name, src)


def _add_unique_name(items: dict[str, list[str]], element: str, src: str) -> None:
    found = None
    for name in items:
        if is_similar(element, name):
            found = name
            break
    if found is None:
        items[element] = [src]
        return
    if _accent_count(element) > _accent_count(found):
        _rename_key(items, found, element)
        found = element
    if src in items[found]:
        return
    items[found].append(src)


def condition_names(vernacular: dict[str, list[str]], cdate: str) -> tuple[str, int]:
    """Merge vernacular names across sources and format them.

    Each name carries its Bioref citations. Return (text, count).
    """
    if not vernacular:
        return "", 0

    items: dict[str, list[str]] = {}
    for src, names in vernacular.items():
        for name in names:
            add_if_needed(items, name, src)

    count = len(items)
    out = []
    for name, refs in items.items():
        refs_text = "{{,}}".join(f"{{{{Bioref|{r}|{cdate}|ref}}}}" for r in refs)
        out.append(name + refs_text)
    return ", ".join(out), count


@lru_cache(maxsize=1)
def _load_countries() -> dict[str, dict[str, str]]:
    """Load the country table."""
    with (DATA_DIR / "countries.yaml").open(encoding="utf-8") as fh:
        data: dict[str, dict[str, str]] = yaml.safe_load(fh)
        return data


def country_data_by_code(code: str) -> str:
    """Return a wikilink for an ISO country code.

    Return the code unlinked if unknown: some sources emit non
    ISO 3166 codes with no Wikipedia page.
    """
    countries = _load_countries()
    entry = countries.get(code)
    if entry is None:
        return code
    if entry["texte_affiche"] == entry["nom_page"]:
        return f"[[{entry['nom_page']}]]"
    return f"[[{entry['nom_page']}|{entry['texte_affiche']}]]"


@lru_cache(maxsize=1)
def _load_wgsrpd() -> dict[str, dict[str, str]]:
    """Load the WGSRPD table."""
    with (DATA_DIR / "wgsrpd.yaml").open(encoding="utf-8") as fh:
        data: dict[str, dict[str, str]] = yaml.safe_load(fh)
        return data


def wgsrpd_data_by_code(code: str) -> str:
    """Return a wikilink for a WGSRPD level-3 code.

    Without a French article, use {{Lien}} to the English one, with
    `fr` only if known. With no article at all, return the plain
    translation. Unknown codes are returned unlinked.
    """
    wgsrpd = _load_wgsrpd()
    entry = wgsrpd.get(code)
    if entry is None:
        return code
    if entry.get("lien"):
        result = f"{{{{Lien|langue={entry['langue']}|trad={entry['trad']}"
        if entry.get("fr"):
            result += f"|fr={entry['fr']}"
        return result + "}}"
    if "nom_page" not in entry:
        return entry["texte_affiche"]
    if entry["texte_affiche"] == entry["nom_page"]:
        return f"[[{entry['nom_page']}]]"
    return f"[[{entry['nom_page']}|{entry['texte_affiche']}]]"


@lru_cache(maxsize=1)
def _load_wgsrpd_continents() -> dict[str, str]:
    """Load the level-3 to level-1 WGSRPD mapping."""
    with (DATA_DIR / "wgsrpd_continents.yaml").open(encoding="utf-8") as fh:
        data: dict[str, str] = yaml.safe_load(fh)
        return data


def wgsrpd_continents_for_codes(codes: list[str]) -> list[str]:
    """Return the level-1 codes covering a list of level-3 codes.

    Sorted by translated name. Unknown codes are ignored.
    """
    mapping = _load_wgsrpd_continents()
    continents = {mapping[code] for code in codes if code in mapping}
    return sorted(continents, key=wgsrpd_data_by_code)
