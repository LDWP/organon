"""Map source languages to Wiktionary `{{langue}}` codes.

Sources use ISO 639-3, ISO 639-1 or English names. The output is
ISO 639-1 when it exists, else ISO 639-3. Unknown languages yield
None.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from typing import NamedTuple

import yaml

from organon.core.rendering.support import DATA_DIR

# ISO 639-2 "undetermined": key for names without a usable language.
# Never rendered on Wikipedia, which only reads "fr".
LANGUE_INDETERMINEE = "und"

# Name aliases missing from the ISO table (639-2 and 639-3 name
# modern Greek differently).
_ALIAS_NOMS = {"greek": "ell"}

# Individual languages mapped to their macrolanguage. Not done for
# cmn: Wiktionary keeps Mandarin (cmn) apart from Chinese (zh).
_RATTACHEMENTS = {"swh": "swa", "npi": "nep"}


class _Langues(NamedTuple):
    vers_code: dict[str, str]
    vers_nom: dict[str, str]


@lru_cache(maxsize=1)
def _charger() -> _Langues:
    """Index `data/langues.yaml`, from SIL's iso-639-3.tab.

    Maps every 639-1, 639-2/B or 639-3 code, and every lowercase
    English name, to its output code.
    """
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with (DATA_DIR / "langues.yaml").open(encoding="utf-8") as fh:
        table = yaml.load(fh, Loader=loader)
    vers_code: dict[str, str] = {}
    noms: list[tuple[str, str, bool]] = []
    for id3, (part1, part2b, nom) in table.items():
        sortie = part1 or id3
        for code in (id3, part1, part2b):
            if code:
                vers_code[code] = sortie
        noms.append((nom.lower(), sortie, bool(part1)))
        sans_precision = re.sub(r"\s*\([^)]*\)", "", nom).strip().lower()
        if sans_precision != nom.lower():
            noms.append((sans_precision, sortie, bool(part1)))
    for individuelle, macro in _RATTACHEMENTS.items():
        vers_code[individuelle] = vers_code[macro]
    # On equal names the language with a 639-1 code wins (e.g. "Malay"
    # is ms, not zlm/zsm); between two others the name is ambiguous.
    vers_nom: dict[str, str] = {}
    prioritaires: set[str] = set()
    ambigus: set[str] = set()
    for nom, sortie, a_part1 in sorted(noms, key=lambda n: not n[2]):
        if nom not in vers_nom:
            vers_nom[nom] = sortie
            if a_part1:
                prioritaires.add(nom)
        elif vers_nom[nom] != sortie and nom not in prioritaires:
            ambigus.add(nom)
    for nom in ambigus:
        del vers_nom[nom]
    vers_nom.update({nom: vers_code[code] for nom, code in _ALIAS_NOMS.items()})
    return _Langues(vers_code, vers_nom)


def code_langue(valeur: str | None) -> str | None:
    """Return the Wiktionary code of a code or English name.

    None if empty or absent from the standard.
    """
    v = (valeur or "").strip().lower()
    langues = _charger()
    # A 2-3 letter string is a code, never a name.
    if len(v) <= 3:
        return langues.vers_code.get(v)
    return langues.vers_nom.get(v) or langues.vers_code.get(v)


def groupe_par_langue(paires: Iterable[tuple[str | None, str | None]]) -> dict[str, list[str]]:
    """Group (source language, name) pairs by Wiktionary code.

    Keep order and drop duplicates and empty names. Names without a
    usable language go under `LANGUE_INDETERMINEE`.
    """
    out: dict[str, list[str]] = {}
    for langue, nom in paires:
        if nom:
            noms = out.setdefault(code_langue(langue) or LANGUE_INDETERMINEE, [])
            if nom not in noms:
                noms.append(nom)
    return out
