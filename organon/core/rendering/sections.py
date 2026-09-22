"""Article rendering, one section at a time.

Each `render_*` function turns the typed `Struct` into one section
of the final wikitext. `render_taxobox` takes the stub list
precomputed, to stay independent of the selector engine; see
`organon.core.rendering.engine.render`.
"""

from __future__ import annotations

from operator import itemgetter

from organon.core.config import GenerateOptions
from organon.core.models import FOOTER_LINK, LinkEntry, PageRef, RankName, Struct
from organon.core.registry import get_module
from organon.core.rendering.grammar import (
    link_for_author,
    link_for_basionym,
    link_for_synonym,
    wp_agree_adjective,
    wp_apply_italics,
    wp_definite_rank,
    wp_extinct_rank,
    wp_indefinite_rank,
    wp_is_infraspecific,
    wp_is_more_specific_rank,
    wp_is_species_or_below,
    wp_rank_name,
)
from organon.core.rendering.support import (
    condition_names,
    country_data_by_code,
    find_homonym,
    format_author,
    retrieval_dates,
    use_columns,
    wgsrpd_continents_for_codes,
    wgsrpd_data_by_code,
    wrap_in_columns,
)

__all__ = [
    "HOMONYM_CATEGORY_RANKS",
    "compute_ext_link_items",
    "compute_rank_lines",
    "compute_rank_names",
    "compute_rank_text",
    "existing_categories",
    "join_and",
    "render_description",
    "render_distribution",
    "render_etymology",
    "render_footer",
    "render_intro",
    "render_lower_taxa",
    "render_original",
    "render_references_items",
    "render_see_also",
    "render_subtaxon_line",
    "render_systematics",
    "render_taxobox",
    "selected_homonym_category",
]

# Kingdoms using "nom correct" rather than "nom valide".
_KINGDOMS_CORRECT_NAME = {"végétal", "champignon", "algue", "bactérie", "archaea"}

# Ranks whose article is the main page of its homonymous category.
HOMONYM_CATEGORY_RANKS = {"embranchement", "classe", "ordre", "famille"}

# Member count from which a missing category may be created
# (WP:OVERCAT, point 3).
_HOMONYM_CATEGORY_THRESHOLD = 10


def existing_categories(struct: Struct) -> dict[str, bool] | None:
    """Return the existence map of candidate categories, if known."""
    return struct.links.get("wikimedia", {}).get("existing_categories")


def _main_category_applies(struct: Struct) -> bool:
    """Return True if {{catégorie principale}} applies.

    It points to the homonymous category, which must be applied and
    exist. If existence is unchecked, assume it does.
    """
    if selected_homonym_category(struct) != struct.taxon.name:
        return False
    existence = existing_categories(struct)
    return existence is None or existence.get(struct.taxon.name, False)


def selected_homonym_category(struct: Struct) -> str | None:
    """Return the homonymous category to apply, or None.

    The taxon's own if it exists on frwiki or may reach the threshold,
    else the first existing higher rank. Only a known, complete count
    below the threshold rules out the taxon's own category. Higher
    ranks have no count; only their existence matters.
    """
    taxon = struct.taxon
    if taxon.rank not in HOMONYM_CATEGORY_RANKS:
        return None
    existence = existing_categories(struct)
    if existence is None or existence.get(taxon.name):
        return taxon.name
    subtaxa = struct.subtaxa
    threshold_excluded = (
        subtaxa is not None
        and bool(subtaxa.items)
        and not subtaxa.truncated
        and len(subtaxa.items) < _HOMONYM_CATEGORY_THRESHOLD
    )
    if not threshold_excluded:
        return taxon.name
    for parent in struct.ranks:
        if parent.rank in HOMONYM_CATEGORY_RANKS and existence.get(parent.name):
            return parent.name
    return None


# Parent rank cited in the intro, e.g. "famille de l'ordre des X".
# Other ranks cite the family. Values are the next canonical rank
# up, skipping intermediate ones; `embranchement` has no entry.
_CITED_PARENT_RANK: dict[str, str] = {
    "famille": "ordre",
    "ordre": "classe",
    "classe": "embranchement",
}

# Section -> (render if plan is false, render if plan is true).
_EMPTY_RENDER_CASES: dict[str, tuple[bool, bool]] = {
    "repartition": (True, True),
    "description": (True, True),
    "etymologie": (False, True),
    "inf": (False, True),
    "originale": (False, True),
    "externes": (False, True),
}


def _renders_when_empty(section: str, options: GenerateOptions) -> bool:
    """Return True if an empty `section` is still rendered."""
    case = _EMPTY_RENDER_CASES.get(section)
    if case is None:
        return False
    return case[1] if options.plan else case[0]


def render_intro(struct: Struct) -> str:
    """Render the introductory sentence."""
    cited_rank = _CITED_PARENT_RANK.get(struct.taxon.rank or "", "famille")
    parent = None
    for rank in struct.ranks:
        if rank.rank == cited_rank:
            cited_name = wp_rank_name(cited_rank, link=True, capitalize=False, plural=False)
            cited_taxon = wp_apply_italics(rank.name, cited_rank, struct.kingdom, link=True)
            parent = (
                (wp_definite_rank(cited_rank) or "") + (cited_name or "") + " des " + cited_taxon
            )
            break

    link = wp_indefinite_rank(struct.taxon.rank)
    rank_name = wp_rank_name(struct.taxon.rank, link=True, capitalize=False, plural=False)
    styled_name = wp_apply_italics(struct.taxon.name, struct.taxon.rank, struct.kingdom)

    if link is None or rank_name is None:
        sentence = f"'''{styled_name}''' est un taxon "
    elif wp_is_species_or_below(struct.taxon.rank):
        sentence = f"'''{styled_name}''' est {link}{rank_name} "
    else:
        sentence = f"Les '''{styled_name}''' sont {link}{rank_name} "

    if struct.taxon.extinct:
        extinct = wp_extinct_rank(struct.taxon.rank) or wp_agree_adjective("éteint", "masculine")
        sentence += f"{extinct} "

    if parent:
        sentence += "de " + parent + ".\n"
    else:
        sentence += ".\n"
    return sentence


def compute_rank_lines(struct: Struct) -> list[tuple[str, str, str]]:
    """Return (rank, name, `{{Taxobox | …}}` line) for each parent.

    Order follows `struct.rangs`, nearest first. Lines include
    homonyms and extinction. Shared with the API, which exposes the
    ranks to compare classifications.
    """
    kingdom = struct.kingdom
    ranks = struct.ranks
    if kingdom == "algue":
        ranks = [r for r in ranks if r.rank != "empire"]

    lines: list[tuple[str, str, str]] = []
    for r in ranks:
        # The only place where an unknown rank (None) becomes visible:
        # "NOTFOUND" tells the editor to fix it instead of leaking
        # "Taxobox | None" into the wikitext.
        rank = r.rank or "NOTFOUND"
        extinct = " | éteint=oui" if r.extinct else ""
        homonym_page, homonym = find_homonym(r.name, kingdom)
        taxobox = f"{{{{Taxobox | {rank}"
        if homonym is None:
            taxobox += f" | {r.name}"
        elif homonym_page:
            taxobox += f" | {{{{Lien vers une page d'homonymie|{homonym}}}}}"
        else:
            taxobox += f" | {homonym} | {r.name}"
        taxobox += f"{extinct} }}}}"
        lines.append((rank, r.name, taxobox))
    return lines


def render_taxobox(struct: Struct, options: GenerateOptions, stub: list[str]) -> str:
    """Render from `{{ébauche}}` to `{{Taxobox fin}}`."""
    result = ""
    result += "{{ébauche|" + "|".join(stub) + "}}\n" if stub else "{{ébauche}}\n"

    taxon, rank, kingdom = struct.taxon.name, struct.taxon.rank, struct.kingdom
    displayed_taxon = wp_apply_italics(taxon, rank, kingdom)
    image = struct.image.get("image") if struct.image else None
    caption = struct.image.get("legende") if struct.image else None
    image = image or "<!-- insérez une image -->"
    caption = caption or "<!-- insérez légende descriptive de l'image -->"
    classification = f"classification={struct.classification_taxobox}"
    cache = " |règne=cacher " if struct.hide_kingdom else ""

    result += (
        f"{{{{Taxobox début | {kingdom} | {displayed_taxon} | {image} | {caption} | "
        f"{classification}{cache}}}}}\n"
    )

    rank_lines = compute_rank_lines(struct)
    result += "\n".join(line for _, _, line in reversed(rank_lines))
    result += "\n"

    extinct = " | éteint=oui" if struct.taxon.extinct else ""
    author = (
        struct.taxon.resolved_author
        if struct.taxon.resolved_author is not None
        else format_author(struct.taxon.author)
    )
    result += f"{{{{Taxobox taxon | {kingdom} | {rank} | {taxon} | {author}{extinct} }}}}\n"

    iucn = struct.links.get("iucn")
    is_species_or_below = rank == "espèce" or wp_is_more_specific_rank(rank, "espèce")
    if iucn and iucn.get("risk") and is_species_or_below:
        criterion = f" | {iucn['criterion']}" if iucn.get("criterion") else ""
        result += f"{{{{Taxobox UICN | {iucn['risk']}{criterion} }}}}\n"

    cites = struct.links.get("cites")
    if cites and cites.get("appendix"):
        date = cites.get("date", "")
        previous = cites.get("precision", "")
        result += f"{{{{Taxobox CITES | {cites['appendix']} | {date} | {previous} }}}}\n"

    result += "{{Taxobox fin}}\n"
    return result


def join_and(items: list[str]) -> str:
    """Join with commas and "et" before the last item."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    text = items[0]
    for i in range(1, len(items)):
        text += " et " + items[i] if i == len(items) - 1 else ", " + items[i]
    return text


def compute_rank_names(items: list[RankName]) -> dict[str, tuple[str, str]]:
    """Return (plural, singular) rank names, keyed by rank key.

    One entry per distinct rank of `liste`, in first-seen order. The
    frontend recomputes the rank text from it as boxes are checked.
    """
    rank_names: dict[str, tuple[str, str]] = {}
    for subtaxon in items:
        if subtaxon.rank is None or subtaxon.rank in rank_names:
            continue
        plural = wp_rank_name(subtaxon.rank, link=False, capitalize=False, plural=True)
        if plural is None:
            continue
        singular = (
            wp_rank_name(subtaxon.rank, link=False, capitalize=False, plural=False) or plural
        )
        rank_names[subtaxon.rank] = (plural, singular)
    return rank_names


def compute_rank_text(items: list[RankName]) -> tuple[str, str, str]:
    """Return `(rank_text, rank_text_singular, default_rank)`.

    The first two are the rank names found in `liste`, plural and
    singular ("espèces et sous-espèces"). `default_rank` is the first
    one, plural, used for items without their own rank.
    """
    rank_names = compute_rank_names(items)
    if not rank_names:
        return "taxons de rang inférieur", "taxon de rang inférieur", "espèce"

    rank_text = join_and([plural for plural, _ in rank_names.values()])
    rank_text_singular = join_and([singular for _, singular in rank_names.values()])
    default_rank = next(iter(rank_names.values()))[0]
    return rank_text, rank_text_singular, default_rank


def render_subtaxon_line(
    subtaxon: RankName, kingdom: str, default_rank: str, taxon_rank: str | None
) -> str:
    """Render one sub-taxon bullet line.

    Wikilinked when more specific than `taxon_rang`, except
    infraspecific ranks, which rarely have an article.
    """
    displayed_rank = subtaxon.rank or default_rank
    author = " " + format_author(subtaxon.author) if subtaxon.author else ""
    wikilink = wp_is_more_specific_rank(displayed_rank, taxon_rank) and not wp_is_infraspecific(
        displayed_rank
    )
    target = wp_apply_italics(subtaxon.name, displayed_rank, kingdom, link=wikilink)
    if subtaxon.extinct:
        target = "† " + target
    return f"* {target}{author}\n"


def render_lower_taxa(struct: Struct, options: GenerateOptions) -> str:
    """Render the sub-taxa section."""
    cdate = retrieval_dates()
    subtaxa = struct.subtaxa
    if subtaxa is None or not subtaxa.items:
        if _renders_when_empty("inf", options):
            return "\n== Liste des taxons de rang inférieur ==\n{{Section vide ou incomplète}}\n"
        return ""

    rank_text, _, default_rank = compute_rank_text(subtaxa.items)
    module_source = subtaxa.source

    ret = f"\n== Liste des {rank_text} ==\nSelon {{{{Bioref|{module_source}|{cdate}}}}} :\n"

    ret0 = ""
    for subtaxon in sorted(subtaxa.items, key=lambda s: s.name):
        ret0 += render_subtaxon_line(subtaxon, struct.kingdom, default_rank, struct.taxon.rank)

    if use_columns(len(subtaxa.items), options):
        ret += wrap_in_columns(ret0)
    else:
        ret += ret0

    if subtaxa.truncated:
        ret += (
            "ATTENTION : liste des sous-taxons tronquée car trop longue. "
            "Utilisez '-limite-listes' pour modifier ce comportement.\n"
        )

    return "\n" + ret


def render_systematics(struct: Struct, options: GenerateOptions) -> str:
    """Render the "Systématique" section."""
    cdate = retrieval_dates()
    ret = "== Systématique ==\n"

    ref = struct.classification
    target_text = wp_apply_italics(struct.taxon.name, struct.taxon.rank, struct.kingdom)
    author_page = link_for_author(struct.kingdom)
    word = "[[nom correct]]" if struct.kingdom in _KINGDOMS_CORRECT_NAME else "[[nom valide]]"

    if struct.taxon.author:
        ret += f"Le {word} complet (avec [[{author_page}|auteur]]) de ce taxon est " + target_text
    else:
        ret += f"Le {word} de ce taxon est " + target_text

    if struct.taxon.author:
        # Unlike the {{Taxobox taxon}} line, which uses
        # `resolved_author`, this sentence deliberately uses the raw
        # author with a basic "et al." replacement. Do not merge the
        # two.
        ret += " " + format_author(struct.taxon.author)
    ret += f"{{{{Bioref|{ref}|{cdate}|ref}}}}.\n"
    if struct.basionym is None:
        ret += "\n"

    if struct.basionym is not None:
        basionym = link_for_basionym(struct.kingdom)
        target_text = wp_apply_italics(struct.basionym.name, struct.taxon.rank, struct.kingdom)
        parts = struct.basionym.name.split(" ")
        author = " " + format_author(struct.basionym.author) if struct.basionym.author else ""
        if len(parts) == 2:
            ret += (
                f"L'espèce a été initialement classée dans le genre ''[[{parts[0]}]]'' sous le "
                f"{basionym} {target_text}{author}"
                f"{{{{Bioref|{struct.basionym.source}|{cdate}|ref}}}}.\n\n"
            )
        else:
            ret += (
                f"Le {basionym} de ce taxon est : {target_text}{author}"
                f"{{{{Bioref|{struct.basionym.source}|{cdate}|ref}}}}\n\n"
            )

    if struct.type_taxon is not None:
        t = struct.type_taxon
        target_text = wp_apply_italics(t.name, t.rank, struct.kingdom, link=True)
        if t.author:
            target_text += " " + t.author
        if t.rank == "espèce":
            type_label = "[[espèce type]]"
        elif t.rank == "genre":
            type_label = "[[genre type]]"
        else:
            text = (wp_definite_rank(t.rank) or "le ") + (t.rank or "taxon")
            type_label = (
                text[:1].upper() + text[1:] if text else text
            ) + " [[Type (biologie)|type]]"
        ret += f"{type_label} est {target_text}{{{{Bioref|{t.source}|{cdate}|ref}}}}.\n\n"

    vernacular_fr = struct.vernacular_names("fr")
    if vernacular_fr:
        text, count = condition_names(vernacular_fr, cdate)
        phrase = (
            "les [[nom vernaculaire|noms vernaculaires]] ou [[nom normalisé|normalisés]] suivants"
            if count > 1
            else "le [[nom vernaculaire]] ou [[nom normalisé|normalisé]] suivant"
        )
        ret += f"Ce taxon porte en français {phrase} : {text}."

        if struct.other_names:
            # Statuses merged per source to reuse condition_names.
            # Always a second sentence: "également" needs the first.
            others_by_source = {
                source: [name for names in statuses.values() for name in names]
                for source, statuses in struct.other_names.items()
            }
            others_text, _ = condition_names(others_by_source, cdate)
            if others_text:
                ret += f" Ce taxon est également nommé {others_text}."

        ret += "\n\n"

    if struct.synonyms is not None and struct.synonyms.items:
        target = link_for_synonym(struct.kingdom)
        target_text = wp_apply_italics(struct.taxon.name, struct.taxon.rank, struct.kingdom)
        word = "synonymes" if len(struct.synonyms.items) > 1 else "synonyme"
        phrase = f"{target_text} a pour [[{target}|{word}]]"
        ret += f"{phrase}{{{{Bioref|{struct.synonyms.source}|{cdate}|ref}}}} :\n"

        ret_t = []
        for s in struct.synonyms.items:
            use_wikilink = options.synonym_links
            synonym_rank = s.rank or struct.taxon.rank
            if (
                use_wikilink
                and wp_is_species_or_below(synonym_rank)
                and not options.infraspecific_links
            ):
                use_wikilink = False
            x = s.rank or struct.taxon.rank
            target_text = wp_apply_italics(s.name, x, struct.kingdom, link=use_wikilink)
            author = " " + format_author(s.author) if s.author else ""
            ret_t.append(f"* {target_text}{author}\n")

        if options.sort_synonyms:
            ret_t.sort()
        ret0 = "".join(ret_t)
        if use_columns(len(struct.synonyms.items), options):
            ret += wrap_in_columns(ret0)
        else:
            ret += ret0

        if struct.synonyms.truncated:
            ret += (
                "ATTENTION : liste des synonymes tronquée car trop longue. "
                "Utilisez '-limite-listes' pour modifier ce comportement.\n"
            )

    return "\n\n" + ret if ret else ""


def render_description(struct: Struct, options: GenerateOptions) -> str:
    """Render the "Description" section."""
    result = "\n== Description ==\n"
    description = struct.description
    if not description:
        if _renders_when_empty("description", options):
            return result + "{{Section vide ou incomplète}}\n"
        return ""
    for ref, items in description.items():
        result += ". ".join(items)
        result += f"{{{{Bioref|{ref}|ref}}}}."
    return result + "\n"


def render_distribution(struct: Struct, options: GenerateOptions) -> str:
    """Render the "Répartition" section."""
    cdate = retrieval_dates()
    result = "\n== Répartition ==\n"
    if not struct.distribution:
        if _renders_when_empty("repartition", options):
            return result + "{{Section vide ou incomplète}}\n"
        return ""

    source = ""
    # `introduced` and `extinct` are subsets of `certain` and
    # `uncertain`: removed from their parent bucket for a dedicated
    # clause per status, as for {{WGSRPD}}.
    certain: list[str] = []
    uncertain: list[str] = []
    introduced: list[str] = []
    extinct: list[str] = []
    wgsrpd_certain: list[str] = []
    wgsrpd_uncertain: list[str] = []
    wgsrpd_introduced: list[str] = []
    wgsrpd_extinct: list[str] = []
    for ref, entry in struct.distribution.items():
        source = ref
        # POWO emits WGSRPD codes, not ISO ones.
        translated_code = wgsrpd_data_by_code if ref == "powo" else country_data_by_code
        certain.extend(
            translated_code(code) for code in entry.certain if code not in entry.introduced
        )
        uncertain.extend(
            translated_code(code) for code in entry.uncertain if code not in entry.extinct
        )
        introduced.extend(translated_code(code) for code in entry.introduced)
        extinct.extend(translated_code(code) for code in entry.extinct)
        if ref == "powo":
            wgsrpd_certain.extend(code for code in entry.certain if code not in entry.introduced)
            wgsrpd_uncertain.extend(code for code in entry.uncertain if code not in entry.extinct)
            wgsrpd_introduced.extend(entry.introduced)
            wgsrpd_extinct.extend(entry.extinct)

    certain = sorted(dict.fromkeys(certain))
    uncertain = sorted(dict.fromkeys(uncertain))
    introduced = sorted(dict.fromkeys(introduced))
    extinct = sorted(dict.fromkeys(extinct))
    wgsrpd_certain = sorted(dict.fromkeys(wgsrpd_certain))
    wgsrpd_uncertain = sorted(dict.fromkeys(wgsrpd_uncertain))
    wgsrpd_introduced = sorted(dict.fromkeys(wgsrpd_introduced))
    wgsrpd_extinct = sorted(dict.fromkeys(wgsrpd_extinct))

    if len(struct.distribution) == 1:
        if wgsrpd_certain or wgsrpd_uncertain or wgsrpd_introduced or wgsrpd_extinct:
            result += "{{WGSRPD"
            if wgsrpd_certain:
                result += f"|certain={','.join(wgsrpd_certain)}"
            if wgsrpd_uncertain:
                result += f"|incertain={','.join(wgsrpd_uncertain)}"
            if wgsrpd_introduced:
                result += f"|introduit={','.join(wgsrpd_introduced)}"
            if wgsrpd_extinct:
                result += f"|eteint={','.join(wgsrpd_extinct)}"
            result += (
                f"|source=[[Plants of the World Online|POWO]]{{{{Bioref|{source}|{cdate}|ref}}}}"
            )
            result += "}}\n"
        total = len(certain) + len(uncertain) + len(introduced) + len(extinct)
        if total > _DISTRIBUTION_LIST_THRESHOLD:
            result += _distribution_summary_and_list(
                certain, uncertain, introduced, extinct, wgsrpd_certain, source, cdate
            )
        else:
            result += _distribution_phrase(certain, uncertain, introduced, extinct, source, cdate)
    else:
        result += (
            "''Une distribution issue de plusieurs sources existe. Non implémenté pour le "
            "moment''\n"
        )
    return result


def _distribution_phrase(
    certain: list[str],
    uncertain: list[str],
    introduced: list[str],
    extinct: list[str],
    source: str,
    cdate: str,
) -> str:
    """Render one clause per status.

    `certain` stays unqualified. A lone status gets its own wording
    instead of a misleading generic "est présent".
    """
    if not (certain or uncertain or introduced or extinct):
        return ""
    ref = f"{{{{Bioref|{source}|{cdate}|ref}}}}"

    if extinct and not (certain or uncertain or introduced):
        return f"Ce taxon est éteint dans {_place(extinct)}{ref} : {', '.join(extinct)}.\n"
    if introduced and not (certain or uncertain or extinct):
        return (
            f"Ce taxon est introduit dans {_place(introduced)}{ref} : {', '.join(introduced)}.\n"
        )
    if uncertain and not (certain or introduced or extinct):
        return (
            f"La présence de ce taxon est incertaine dans {_place(uncertain)}{ref} : "
            f"{', '.join(uncertain)}.\n"
        )

    clauses = []
    if certain:
        clauses.append(", ".join(certain))
    if introduced:
        clauses.append(f"introduit en {', '.join(introduced)}")
    if uncertain:
        clauses.append(f"de présence incertaine en {', '.join(uncertain)}")
    if extinct:
        clauses.append(f"éteint en {', '.join(extinct)}")

    if certain:
        header = f"Ce taxon est présent dans {_place(certain)}"
    else:
        header = "Statut de ce taxon par pays et région"
    return f"{header}{ref} : {'; '.join(clauses)}.\n"


def _place(items: list[str]) -> str:
    """Return "country or region" with number agreement."""
    return "le pays ou la région suivant" if len(items) == 1 else "les pays et régions suivants"


# Total entries above which the inline sentence becomes unreadable:
# switch to a count summary plus a list grouped by status.
_DISTRIBUTION_LIST_THRESHOLD = 10

# Entries per status above which the comma list is too long: use
# a collapsed {{Liste déroulante}} holding a {{colonnes}} list.
_STATUS_COLUMNS_THRESHOLD = 15


def _continents_link(n: int) -> str:
    """Return "continent(s)" linked to the WGSRPD article.

    L1 regions (e.g. Pacific) are not all real continents.
    """
    text = "continent" if n == 1 else "continents"
    return (
        "{{Lien|trad=World Geographical Scheme for Recording Plant Distributions|langue=en|"
        "fr=Système géographique mondial d'enregistrement de la répartition des plantes|"
        f"texte={text}}}}}"
    )


_NUMBER_WORDS = {
    0: "zéro",
    1: "un",
    2: "deux",
    3: "trois",
    4: "quatre",
    5: "cinq",
    6: "six",
    7: "sept",
    8: "huit",
    9: "neuf",
    10: "dix",
    11: "onze",
    12: "douze",
    13: "treize",
    14: "quatorze",
    15: "quinze",
    16: "seize",
}


def _spell_out(n: int) -> str:
    """Spell out small numbers; above 16 fall back to digits."""
    return _NUMBER_WORDS.get(n, str(n))


def _french_list(items: list[str]) -> str:
    """Join as "A", "A et B" or "A, B et C"."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " et " + items[-1]


def _distribution_summary_and_list(
    certain: list[str],
    uncertain: list[str],
    introduced: list[str],
    extinct: list[str],
    wgsrpd_certain: list[str],
    source: str,
    cdate: str,
) -> str:
    """Render a count summary and a list grouped by status.

    Replaces `_distribution_phrase` above the list threshold.
    """
    ref = f"{{{{Bioref|{source}|{cdate}|ref}}}}"
    # No |ref in the dropdown: {{Bioref}} is a plain inline citation
    # there, the footnote is already set by `ref` above.
    citation = f"{{{{Bioref|{source}|{cdate}}}}}"

    result = ""
    ref_used = False
    continents = wgsrpd_continents_for_codes(wgsrpd_certain) if certain else []
    if continents:
        continents_text = _french_list([f"en {wgsrpd_data_by_code(c)}" for c in continents])
        result += (
            f"Ce taxon est présent sur {_spell_out(len(continents))} "
            f"{_continents_link(len(continents))}{ref} : {continents_text}. "
        )
        ref_used = True

    clauses = []
    if certain:
        suffix = "pays ou région" if len(certain) == 1 else "pays et régions"
        clauses.append(f"[[indigène (écologie)|indigène]] dans {len(certain)} {suffix}")
    if introduced:
        suffix = "autre" if len(introduced) == 1 else "autres"
        clauses.append(f"introduit dans {len(introduced)} {suffix}")
    if uncertain:
        suffix = "autre" if len(uncertain) == 1 else "autres"
        clauses.append(f"de présence incertaine dans {len(uncertain)} {suffix}")
    if extinct:
        suffix = "pays ou région" if len(extinct) == 1 else "pays et régions"
        clauses.append(f"éteint dans {len(extinct)} {suffix}")

    result += f"Il est {_french_list(clauses)}"
    if not ref_used:
        result += ref
    result += ".\n\n"

    if certain:
        result += _status_block("Natif", "indigène", certain, citation)
    if introduced:
        result += _status_block("Introduit", "introduit", introduced, citation)
    if uncertain:
        result += _status_block(
            "Présence incertaine", "de présence incertaine", uncertain, citation
        )
    if extinct:
        result += _status_block("Éteint", "éteint", extinct, citation)
    return result


def _status_block(label: str, qualifier: str, items: list[str], citation: str) -> str:
    """Render one status block.

    A comma list up to `_STATUS_COLUMNS_THRESHOLD`, else a collapsed
    {{Liste déroulante}} with source and columns. `qualifier` is
    the adjective used in its title.
    """
    if len(items) <= _STATUS_COLUMNS_THRESHOLD:
        return f"* {label} : {_french_list(items)}.\n"
    lines = "\n".join(f"* {item}" for item in items)
    title = f"Liste des régions et pays dans lesquels ce taxon est {qualifier}"
    return (
        "<center>\n"
        "{{Liste déroulante\n"
        " | width   = 55%\n"
        f" | titre   = {title}\n"
        " | contenu =\n"
        f" Données : {citation}.\n"
        " {{colonnes|taille=18|1=\n"
        f"{lines}\n"
        "}}\n"
        "}}\n"
        "</center>\n"
    )


def render_etymology(struct: Struct, options: GenerateOptions) -> str:
    """Render the "Étymologie" section."""
    cdate = retrieval_dates()
    result = "\n== Étymologie ==\n"
    if struct.etymology is None:
        if _renders_when_empty("etymologie", options):
            return result + "{{Section vide ou incomplète}}\n"
        return ""
    result += f"{struct.etymology.text}{{{{Bioref|{struct.etymology.source}|{cdate}|ref}}}}.\n"
    return result


def render_original(struct: Struct, options: GenerateOptions) -> str:
    """Render the original publication(s) section."""
    if struct.original_publication is None:
        if _renders_when_empty("originale", options):
            return "\n== Publications originales ==\n{{Section vide ou incomplète}}\n"
        return ""

    publications = (
        struct.original_publication
        if isinstance(struct.original_publication, list)
        else [struct.original_publication]
    )
    title = (
        "\n== Publications originales ==\n"
        if len(publications) > 1
        else "\n== Publication originale ==\n"
    )
    result = title
    for publication in sorted(publications):
        result += f"* {publication}\n"
    return result


def compute_ext_link_items(struct: Struct) -> list[tuple[str, str]]:
    """Return unsorted (module_id, wikitext) taxonomic references.

    Built from each module's `render_bioref`, one pair per line.
    Deduplicated by exact line: two modules may resolve the same
    external record.
    """
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for module_id, _data in struct.links.items():
        module = None
        module = get_module(module_id)
        if module is None:
            continue
        rendered = module.render_bioref(struct)
        if not rendered:
            continue
        lines = rendered if isinstance(rendered, list) else [rendered]
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            items.append((module_id, line))
    return items


def _compute_ext_links(struct: Struct) -> list[str]:
    """Return the unsorted taxonomic reference lines."""
    return [wikitext for _module_id, wikitext in compute_ext_link_items(struct)]


def render_references_items(struct: Struct) -> list[tuple[str, str]]:
    """Return (module_id, wikitext) references sorted by wikitext.

    Exposed so the frontend can toggle each reference.
    """
    return sorted(compute_ext_link_items(struct), key=itemgetter(1))


def _page_of(ref: PageRef | None) -> str | None:
    return ref.get("page") if ref else None


def render_see_also(struct: Struct, options: GenerateOptions) -> str:
    """Render the "Liens externes" section."""
    others: list[str] = []

    wikimedia: LinkEntry = struct.links.get("wikimedia", {})
    if any(k in wikimedia for k in ("commons", "wikispecies", "commons_category", "frwiktionary")):
        commons_page = _page_of(wikimedia.get("commons"))
        commons_cat_page = _page_of(wikimedia.get("commons_category"))
        if commons_page and not commons_cat_page:
            others.append(f"commons={commons_page}")
        elif commons_page and commons_cat_page:
            others.extend(
                (
                    f"commons={commons_page}",
                    f"commons2=Category:{commons_cat_page}",
                    f"commons titre2=Catégorie {commons_cat_page}",
                )
            )
        elif not commons_page and commons_cat_page:
            others.extend(
                (
                    f"commons=Category:{commons_cat_page}",
                    f"commons titre=Catégorie {commons_cat_page}",
                )
            )
        if wikispecies_page := _page_of(wikimedia.get("wikispecies")):
            others.append(f"species={wikispecies_page}")
        if wiktionary_page := _page_of(wikimedia.get("frwiktionary")):
            others.append(f"wiktionary={wiktionary_page}")

    ext = _compute_ext_links(struct)
    main_category = _main_category_applies(struct)

    if not ext and not others and not main_category:
        if _renders_when_empty("externes", options):
            return "== Liens externes ==\n{{Section vide ou incomplète}}\n"
        return ""

    result = "== Liens externes ==\n"
    if others:
        result += "{{Autres projets\n"
        for a in sorted(others):
            result += f"| {a}\n"
        result += "}}\n"
    if main_category:
        # TODO: pass {{Catégorie principale|Titre}} when the page title
        # differs from the taxon name (homonymy, e.g. "Elmidae
        # (famille)"); the real target title is unavailable here.
        result += "{{catégorie principale}}\n"
    if ext:
        for e in sorted(ext):
            result += f"* {e}\n"

    return "\n" + result


def render_footer(struct: Struct, notes: bool = False) -> str:
    """Render notes, references, portals and categories."""
    if notes:
        ret = (
            "\n== Notes et références ==\n"
            "=== Notes ===\n{{Références|groupe=note}}\n"
            "=== Références ===\n{{références}}\n"
        )
    else:
        ret = "\n== Notes et références ==\n{{références}}\n"
    footer: LinkEntry = struct.links.get(FOOTER_LINK, {})
    portals = footer.get("portals") or []
    categories = footer.get("categories") or []
    if portals:
        ret += "\n{{Portail|" + "|".join(portals) + "}}\n"
    if categories:
        ret += "\n"
        for c in categories:
            ret += f"[[Catégorie:{c}]]\n"
    return ret
