"""Pure comparison of an article's distribution with the source's.

Two levels: the `{{WGSRPD}}` template (exact codes, POWO) then
prose (a source country is "cited" if its name is in the section).
Findings only; article-only content is never reported.
`valeur_wikidata` holds the article side, `valeur_source` the
source side.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from organon.core.distribution_parser import RepartitionView
from organon.core.models import DistributionEntry
from organon.core.rendering.support import country_data_by_code, wgsrpd_data_by_code
from organon.core.update_diagnosis import Ecart

_PROPRIETE = "Répartition"
_STATUTS = ("certain", "incertain", "introduit", "eteint")
_LIEN_RE = re.compile(r"\[\[(?P<cible>[^\]|]+)(?:\|(?P<lib>[^\]]*))?\]\]")
_LIEN_MODELE_RE = re.compile(r"\{\{\s*Lien\s*\|.*?\bfr\s*=\s*(?P<fr>[^|}]+)", re.IGNORECASE)
_DESAMBIG_RE = re.compile(r"\s*\([^)]*\)$")


@dataclass(frozen=True)
class ComptesRepartition:
    """Counts for "N source countries not cited".

    `absents_article` holds codes at `wgsrpd` level, French names at
    `prose` level.
    """

    n_source: int
    absents_article: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiagnosticRepartition:
    """Findings of a distribution comparison.

    `niveau` is None when no content comparison happened, in which
    case `limites` says why.
    """

    ecarts: list[Ecart] = field(default_factory=list)
    comptes: ComptesRepartition | None = None
    niveau: Literal["wgsrpd", "prose"] | None = None
    limites: list[str] = field(default_factory=list)


def _norm(texte: str) -> str:
    """Casefold, strip accents and punctuation, collapse spaces."""
    sans_accents = unicodedata.normalize("NFD", texte.casefold().replace("’", "'"))
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w']+", " ", sans_accents).split())


def _statuts_source(entry: DistributionEntry) -> dict[str, set[str]]:
    """Return code sets per status, as `render_distribution` does.

    `introduced` and `extinct` are removed from their parent bucket.
    """
    return {
        "certain": set(entry.certain) - set(entry.introduced),
        "incertain": set(entry.uncertain) - set(entry.extinct),
        "introduit": set(entry.introduced),
        "eteint": set(entry.extinct),
    }


def _variantes(code: str, rendu: str) -> list[str]:
    """Return candidate names of a country from its rendered link.

    Empty if the code has no French name (returned unchanged). Data
    tables contain HTML entities.
    """
    if rendu == code:
        return []
    rendu = html.unescape(rendu)
    modele = _LIEN_MODELE_RE.search(rendu)
    if modele:
        return [modele.group("fr").strip()]
    lien = _LIEN_RE.fullmatch(rendu)
    if lien:
        noms = [_DESAMBIG_RE.sub("", lien.group("cible").strip())]
        if lien.group("lib"):
            noms.append(lien.group("lib").strip())
        return noms
    return [] if rendu.startswith("{{") else [rendu]


def _compare_codes(
    article: dict[str, frozenset[str]], entry: DistributionEntry, source: str
) -> DiagnosticRepartition:
    dans_source = _statuts_source(entry)
    statut_article = {c: s for s in _STATUTS for c in article[s]}
    absents: list[str] = []
    differents: list[tuple[str, str, str]] = []
    for statut in _STATUTS:
        for code in sorted(dans_source[statut]):
            vu = statut_article.get(code)
            if vu is None:
                absents.append(code)
            elif vu != statut:
                differents.append((code, vu, statut))

    absents.sort()
    ecarts: list[Ecart] = []
    if absents:
        liste = ", ".join(absents)
        ecarts.append(
            Ecart(
                type="repartition_code_absent_article",
                severite="avertissement",
                propriete=_PROPRIETE,
                valeur_source=liste,
                source=source,
                message=(
                    f"{len(absents)} code(s) WGSRPD de {source} absent(s) de l'article : {liste}."
                ),
            )
        )
    if differents:
        differents.sort()
        ecarts.append(
            Ecart(
                type="repartition_statut_different",
                severite="avertissement",
                propriete=_PROPRIETE,
                valeur_wikidata=", ".join(f"{c} : {a}" for c, a, _ in differents),
                valeur_source=", ".join(f"{c} : {s}" for c, _, s in differents),
                source=source,
                message=(
                    f"{len(differents)} code(s) WGSRPD avec un statut différent entre l'article "
                    f"et {source}."
                ),
            )
        )
    n_source = sum(len(v) for v in dans_source.values())
    return DiagnosticRepartition(
        ecarts=ecarts, comptes=ComptesRepartition(n_source, absents), niveau="wgsrpd"
    )


def _compare_prose(texte: str, entry: DistributionEntry, source: str) -> DiagnosticRepartition:
    traduit = wgsrpd_data_by_code if source == "powo" else country_data_by_code
    codes = dict.fromkeys([*entry.certain, *entry.uncertain, *entry.introduced, *entry.extinct])
    section = _norm(texte)
    non_cites: list[str] = []
    sans_nom: list[str] = []
    n_compares = 0
    for code in codes:
        variantes = _variantes(code, traduit(code))
        if not variantes:
            sans_nom.append(code)
            continue
        n_compares += 1
        if not any(re.search(rf"(?<!\w){re.escape(_norm(v))}(?!\w)", section) for v in variantes):
            non_cites.append(variantes[-1])

    limites = []
    if sans_nom:
        limites.append(
            f"Code(s) sans nom français ignoré(s) de la comparaison : {', '.join(sans_nom)}."
        )
    ecarts: list[Ecart] = []
    if non_cites:
        liste = ", ".join(non_cites)
        ecarts.append(
            Ecart(
                type="repartition_pays_non_cite",
                severite="info",
                propriete=_PROPRIETE,
                valeur_source=liste,
                source=source,
                message=(
                    f"{len(non_cites)} pays ou région(s) de {source} non cité(s) dans la "
                    f"section : {liste}. Peut être couvert par une région "
                    "(ex. « toute l'Europe »)."
                ),
            )
        )
    return DiagnosticRepartition(
        ecarts=ecarts,
        comptes=ComptesRepartition(n_compares, non_cites),
        niveau="prose",
        limites=limites,
    )


def compare_distribution(
    view: RepartitionView, distribution: Mapping[str, DistributionEntry]
) -> DiagnosticRepartition:
    """Compare an article's distribution with `distribution`.

    Only a single source is compared.
    """
    if len(distribution) > 1:
        return DiagnosticRepartition(
            limites=["Répartition issue de plusieurs sources : non comparée."]
        )
    if not distribution:
        return DiagnosticRepartition()
    source, entry = next(iter(distribution.items()))
    if not (entry.certain or entry.uncertain or entry.introduced or entry.extinct):
        return DiagnosticRepartition()

    limites: list[str] = []
    if view.wgsrpd is not None:
        if source == "powo":
            return _compare_codes(view.wgsrpd, entry, source)
        limites.append(
            f"Gabarit WGSRPD de l'article non comparable à {source} (pas de codes WGSRPD)."
        )
    if not view.section_identifiee:
        return DiagnosticRepartition(
            ecarts=[
                Ecart(
                    type="section_repartition_absente",
                    severite="info",
                    propriete=_PROPRIETE,
                    source=source,
                    message=(
                        f"Aucune section de répartition dans l'article, {source} en fournit une."
                    ),
                )
            ],
            limites=[*limites, "Section de répartition non identifiée : non comparée."],
        )
    d = _compare_prose(view.texte, entry, source)
    return DiagnosticRepartition(d.ecarts, d.comptes, d.niveau, [*limites, *d.limites])


def diagnose_distribution(
    view: RepartitionView, distribution: Mapping[str, DistributionEntry]
) -> list[Ecart]:
    """Return only the findings of `compare_distribution`."""
    return compare_distribution(view, distribution).ecarts
