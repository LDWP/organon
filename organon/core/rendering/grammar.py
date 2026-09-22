"""Grammar and rendering of scientific names and ranks.

Rank data comes from `data/ranks.yaml`, not from code. Per-kingdom
lookup tables for author pages, basionym links, categories and
synonyms live here too. Stub, category and portal logic lives in
`organon.core.selectors`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

__all__ = [
    "AdjectiveEntry",
    "CATEGORY_BY_KINGDOM",
    "RankEntry",
    "RankTable",
    "STUB_BY_KINGDOM",
    "link_for_author",
    "link_for_basionym",
    "link_for_synonym",
    "load_rank_table",
    "wp_agree_adjective",
    "wp_apply_italics",
    "wp_definite_rank",
    "wp_extinct_rank",
    "wp_indefinite_rank",
    "wp_is_infraspecific",
    "wp_is_italic",
    "wp_is_more_specific_rank",
    "wp_is_species_or_below",
    "wp_is_valid_rank",
    "wp_rank_name",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


Gender = Literal["masculine", "feminine"]


class RankEntry(BaseModel):
    """Non-derivable primitives of a rank.

    The canonical lowercase name is the YAML key.
    """

    gender: Gender
    below_species: bool
    page: str | None = None
    plural: str | None = None
    invariant: bool = False
    lang_en: bool = False


class AdjectiveEntry(BaseModel):
    """Inflected forms of an adjective and its internal link."""

    masculine_singular: str
    feminine_singular: str
    neutral_singular: str
    masculine_plural: str
    feminine_plural: str
    neutral_plural: str
    internal_link: bool
    page: str


class RankTable(BaseModel):
    """Ranks and adjectives loaded from `ranks.yaml`."""

    ranks: dict[str, RankEntry]
    adjectives: dict[str, AdjectiveEntry]


@lru_cache(maxsize=1)
def load_rank_table(path: Path | None = None) -> RankTable:
    """Load and validate the rank table."""
    target = path or (DATA_DIR / "ranks.yaml")
    with target.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return RankTable.model_validate(raw)


# Rank names with a mute h (elision despite the consonant). Extend
# if a new one appears in ranks.yaml.
_SILENT_H: set[str] = {"hybride"}

_VOWELS = set("aeiouyàâäéèêëïîôöùûü")


def _starts_with_vowel_sound(name: str) -> bool:
    """Return True if `nom` starts with a vowel sound."""
    return bool(name) and (name[0].lower() in _VOWELS or name in _SILENT_H)


def _capitalize(name: str) -> str:
    """Capitalize the first letter only."""
    return name[0].upper() + name[1:] if name else name


def _name_form(lowercase_name: str, entry: RankEntry, capitalize: bool, plural: bool) -> str:
    """Compute one of the four forms (case x number) of a rank name.

    Invariant ranks ignore both. `lang_en` ranks stay an untranslated
    English loan, capitalized and italic through {{lang|en|…}}.
    """
    if entry.invariant:
        return lowercase_name
    if entry.lang_en:
        return f"''{{{{lang|en|{_capitalize(lowercase_name)}}}}}''"
    base = lowercase_name
    if plural:
        base = entry.plural or f"{lowercase_name}s"
    return _capitalize(base) if capitalize else base


def _link_form(lowercase_name: str, entry: RankEntry, capitalize: bool) -> str:
    """Compute a wikilink: [[Nom]], or [[Page|Nom]] if `page` differs.

    Invariant ranks have no page, only placeholder text between dashes.
    `lang_en` ranks link the italic English loan to `page`.
    """
    if entry.invariant:
        return f"— {lowercase_name} —"
    display = _name_form(lowercase_name, entry, capitalize, plural=False)
    if entry.page is None:
        return f"[[{display}]]"
    return f"[[{entry.page}|{display}]]"


# Kingdoms where italics depend on the rank, see wp_is_italic.
_DOMAINS_WITHOUT_SYSTEMATIC_ITALICS: set[str] = {
    "animal",
    "reptile",
    "amphibien",
    "protiste",
    "eucaryote",
}


def wp_is_valid_rank(rank: str | None, table: RankTable | None = None) -> bool:
    """Return True if `rang` is in the rank table."""
    table = table or load_rank_table()
    return rank in table.ranks


def wp_rank_name(
    rank: str | None, link: bool, capitalize: bool, plural: bool, table: RankTable | None = None
) -> str | None:
    """Return the name of a rank for the given options.

    `link` adds a wikilink, `capitalize` and `plural` do as named.
    Unknown ranks and None give "NOTFOUND".
    """
    table = table or load_rank_table()
    if rank is None or not wp_is_valid_rank(rank, table):
        return None
    entry = table.ranks[rank]
    if link:
        return _link_form(rank, entry, capitalize)
    return _name_form(rank, entry, capitalize, plural)


def wp_indefinite_rank(rank: str | None, table: RankTable | None = None) -> str | None:
    """Return the indefinite article of a rank."""
    table = table or load_rank_table()
    if rank is None or not wp_is_valid_rank(rank, table):
        return None
    return "un " if table.ranks[rank].gender == "masculine" else "une "


def wp_definite_rank(rank: str | None, table: RankTable | None = None) -> str | None:
    """Return the definite article of a rank."""
    table = table or load_rank_table()
    if rank is None or not wp_is_valid_rank(rank, table):
        return None
    if _starts_with_vowel_sound(rank):
        return "l'"
    return "le " if table.ranks[rank].gender == "masculine" else "la "


def wp_is_species_or_below(rank: str | None, table: RankTable | None = None) -> bool | None:
    """Return whether the rank is species level or below.

    Used by `wp_est_italique`. "NOTFOUND" if unknown.
    """
    table = table or load_rank_table()
    if rank is None or not wp_is_valid_rank(rank, table):
        return None
    return table.ranks[rank].below_species


def wp_is_more_specific_rank(
    rank: str | None, reference: str | None, table: RankTable | None = None
) -> bool:
    """Return True if `rang` is more specific than `reference`.

    Follows the order of `ranks.yaml`, most specific first. A rank
    absent from the table counts as more specific, so that no valid
    sub-taxon loses its link.
    """
    table = table or load_rank_table()
    order = list(table.ranks)
    if rank not in order or reference not in order:
        return True
    return order.index(rank) < order.index(reference)


def wp_is_infraspecific(rank: str | None, table: RankTable | None = None) -> bool:
    """Return True if `rang` is strictly below species.

    Such taxa rarely have an article, so they are not linked. Unlike
    `below_species`, genus and above are excluded.
    """
    table = table or load_rank_table()
    if not wp_is_valid_rank(rank, table):
        return False
    return rank != "espèce" and wp_is_more_specific_rank(rank, "espèce", table)


def wp_agree_adjective(
    adjective_name: str,
    gender: Gender,
    plural: bool = False,
    table: RankTable | None = None,
) -> str | None:
    """Inflect an adjective of the table by gender and number.

    Wrap it in its internal link if `internal_link`.
    """
    table = table or load_rank_table()
    entry = table.adjectives.get(adjective_name)
    if entry is None:
        return None
    if gender == "masculine":
        form = entry.masculine_plural if plural else entry.masculine_singular
    else:
        form = entry.feminine_plural if plural else entry.feminine_singular
    if entry.internal_link:
        return f"[[{entry.page}|{form}]]"
    return form


def wp_extinct_rank(rank: str | None, table: RankTable | None = None) -> str | None:
    """Return "éteint" agreed with the rank."""
    table = table or load_rank_table()
    if rank is None or not wp_is_valid_rank(rank, table):
        return None
    return wp_agree_adjective("éteint", table.ranks[rank].gender, table=table)


def wp_is_italic(rank: str | None, kingdom: str, table: RankTable | None = None) -> bool:
    """Return True if the name is italicized.

    Always, except for the kingdoms in
    `_DOMAINS_WITHOUT_SYSTEMATIC_ITALICS`, where only species and
    below are.
    """
    if kingdom not in _DOMAINS_WITHOUT_SYSTEMATIC_ITALICS:
        return True
    return bool(wp_is_species_or_below(rank, table))


# Segments of a name italicized separately (infraspecific rank
# abbreviations, hybrid markers). Each match is wrapped in two
# apostrophes, which inside the global italic envelope toggles it to
# roman for that segment only.
_EXCLUSIONS: list[tuple[str, str]] = [
    (r" cl[.]", " ''cl.''"),
    (r"convar[.]", "''convar.''"),
    (r"f[.]sp[.]", "''f.sp.''"),
    (r" f[.]", " ''f.''"),
    (r" gen[.]", " ''gen.''"),
    (r"kl[.]", "''kl.''"),
    (r"nothog[.]", "''nothog.''"),
    (r"nothosp[.]", "''nothosp.''"),
    (r"nothovar[.]", "''nothovar.''"),
    (r" ord[.]", " ''ord.''"),
    (r" fam[.]", " ''fam.''"),
    (r" sect[.]", " ''sect.''"),
    (r" ser[.]", " ''ser.''"),
    (r" sp[.]", " ''sp.''"),
    (r"subg[.]", "''subg.''"),
    (r"subsp[.]", "''subsp.''"),
    (r"Groupe", "''Groupe''"),
    (r" tr[.]", " ''tr.''"),
    (r" var[.]", " ''var.''"),
    (r"×", "''×''"),
    (r"pv", "''pv''"),
    (r"pathovar", "''pathovar''"),
    (r"morphovar", "''morphovar''"),
    (r"phagovar", "''phagovar''"),
    (r"serovar", "''serovar''"),
    (r"chemovar", "''chemovar''"),
    (r"cultivar", "''cultivar''"),
    (r"chemoform", "''chemoform''"),
    (r"chemotype", "''chemotype''"),
    (r"morphotype", "''morphotype''"),
    (r"pathotype", "''pathotype''"),
    (r"phagotype", "''phagotype''"),
    (r"lysotype", "''lysotype''"),
    (r"phase", "''phase''"),
    (r"serotype", "''serotype''"),
    (r"state", "''state''"),
    (r"forma specialis", "''forma specialis''"),
]
# Trailing negative lookahead instead of \b: a dot followed by a
# space is not a word boundary (e.g. "var. macrocarpum").
_EXCLUSIONS_COMPILED = [
    (re.compile(r"\b" + pattern + r"(?!\w)"), repl) for pattern, repl in _EXCLUSIONS
]


def _without_empty_italics(wikitext: str) -> str:
    """Remove empty italic pairs (four apostrophes) left by exclusions.

    MediaWiki would read them as bold plus a literal apostrophe.
    """
    while "''''" in wikitext:
        wikitext = wikitext.replace("''''", "")
    return wikitext


def wp_apply_italics(
    taxon: str,
    rank: str | None,
    kingdom: str,
    link: bool = False,
    sublink: bool = True,
    table: RankTable | None = None,
) -> str:
    """Return a scientific name as wikitext with italics handled.

    Raise ValueError on an empty `taxon`: a programming error, better
    than an error message silently rendered in the article.
    """
    if not taxon:
        raise ValueError("wp_apply_italics() nécessite un 'taxon' non vide.")

    if not wp_is_italic(rank, kingdom, table):
        return f"[[{taxon}]]" if link else taxon

    ref = taxon
    modified = taxon
    for pattern, repl in _EXCLUSIONS_COMPILED:
        modified = pattern.sub(repl, modified)

    if modified == ref:
        if link:
            return f"''[[{taxon}]]''"
        return f"''{taxon}''" if sublink else taxon

    if link:
        return _without_empty_italics(f"[[{ref}|''{modified}'']]")
    return _without_empty_italics(f"''{modified}''") if sublink else modified


# Per-kingdom tables (links to Wikipedia convention pages).
_AUTHOR_LINKS: dict[str, str] = {
    "algue": "Citation d'auteurs en botanique",
    "animal": "Citation d'auteurs en zoologie",
    "reptile": "Citation d'auteurs en zoologie",
    "amphibien": "Citation d'auteurs en zoologie",
    "archaea": "Citation d'auteurs en bactériologie",
    "bactérie": "Citation d'auteurs en bactériologie",
    "champignon": "Citation d'auteurs en botanique",
    "protiste": "Citation d'auteurs en zoologie",
    "végétal": "Citation d'auteurs en botanique",
    "virus": "Auteur#Dans les sciences et techniques",
    "neutre": "Auteur#Dans les sciences et techniques",
    "eucaryote": "Auteur#Dans les sciences et techniques",
    "procaryote": "Citation d'auteurs en bactériologie",
}


def link_for_author(kingdom: str) -> str:
    """Return the author-citation page for a kingdom."""
    return _AUTHOR_LINKS.get(kingdom, "Auteur#Dans les sciences et techniques")


_BASIONYM_LINKS: dict[str, str] = {
    "algue": "[[basionyme]]",
    "animal": "[[protonyme]]",
    "reptile": "[[protonyme]]",
    "amphibien": "[[protonyme]]",
    "archaea": "[[basionyme]]",
    "bactérie": "[[basonyme]]",
    "champignon": "[[basionyme]]",
    "protiste": "[[basonyme]]",
    "végétal": "[[basionyme]]",
    "virus": "[[basonyme]]",
    "neutre": "[[basionyme]]",
    "eucaryote": "[[basionyme]]",
    "procaryote": "[[basionyme]]",
}


def link_for_basionym(kingdom: str) -> str:
    """Return the basionym wikilink for a kingdom."""
    return _BASIONYM_LINKS.get(kingdom, "[[basionyme]]")


CATEGORY_BY_KINGDOM: dict[str, str] = {
    "algue": "Algue (nom scientifique)",
    "animal": "Animal (nom scientifique)",
    "reptile": "Animal (nom scientifique)",
    "amphibien": "Animal (nom scientifique)",
    "archaea": "Archée (nom scientifique)",
    "bactérie": "Bactérie (nom scientifique)",
    "champignon": "Champignon (nom scientifique)",
    "protiste": "Protiste (nom scientifique)",
    "végétal": "Plante (nom scientifique)",
    "virus": "",
    "neutre": "",
    "eucaryote": "Eucaryote (nom scientifique)",
    "procaryote": "",
}

_SYNONYM_BY_KINGDOM: dict[str, str] = {
    "algue": "Synonyme (taxinomie)",
    "animal": "Synonyme (zoologie)",
    "reptile": "Synonyme (zoologie)",
    "amphibien": "Synonyme (zoologie)",
    "archaea": "Synonyme (taxinomie)",
    "bactérie": "Synonyme (taxinomie)",
    "champignon": "Synonyme (botanique)",
    "protiste": "Synonyme (taxinomie)",
    "végétal": "Synonyme (botanique)",
    "virus": "Synonyme (taxinomie)",
    "neutre": "Synonyme (taxinomie)",
    "eucaryote": "Synonyme (taxinomie)",
    "procaryote": "Synonyme (taxinomie)",
}


def link_for_synonym(kingdom: str) -> str:
    """Return the synonym page for a kingdom."""
    return _SYNONYM_BY_KINGDOM.get(kingdom, "Synonyme (taxinomie)")


STUB_BY_KINGDOM: dict[str, str] = {
    "algue": "algue",
    "animal": "zoologie",
    "reptile": "reptile",
    "amphibien": "amphibien",
    "archaea": "biologie",
    "bactérie": "bactérie",
    "champignon": "champignon",
    "protiste": "protiste",
    "végétal": "botanique",
    "virus": "virus",
    "neutre": "biologie",
    "eucaryote": "biologie",
    "procaryote": "biologie",
}
