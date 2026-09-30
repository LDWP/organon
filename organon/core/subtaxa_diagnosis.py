"""Pure comparison of an article's sub-taxa with the source's.

Findings only (`Ecart`, at most `info`), never a corrected value.
`valeur_wikidata` holds the article side, `valeur_source` the
source side, as in `wikilinks_diagnosis`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from organon.core.update_diagnosis import Ecart

_PROPRIETE = "Taxons inférieurs"


@dataclass(frozen=True)
class ComptesSousTaxons:
    """Counts and missing names per side, article vs source."""

    n_article: int
    n_source: int
    absents_article: list[str] = field(default_factory=list)
    absents_source: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiagnosticSousTaxons:
    """Findings of a sub-taxa comparison.

    `comptes` is None when no content comparison happened, in which
    case `limites` says why.
    """

    ecarts: list[Ecart] = field(default_factory=list)
    comptes: ComptesSousTaxons | None = None
    limites: list[str] = field(default_factory=list)


def _norm(nom: str) -> str:
    """Collapse whitespace in a name."""
    return " ".join(nom.split())


def _distincts(noms: Sequence[str]) -> dict[str, None]:
    """Return the normalized non-empty names as an ordered set."""
    return dict.fromkeys(_norm(n) for n in noms if n.strip())


def compare_subtaxa(
    article_names: Sequence[str] | None,
    source_names: Sequence[str],
    *,
    source: str,
    truncated: bool,
) -> DiagnosticSousTaxons:
    """Compare article and source sub-taxa lists.

    `article_names` None means no list zone was found. `truncated`
    means the source list is incomplete, so its gaps prove nothing.
    """
    if truncated:
        return DiagnosticSousTaxons(
            limites=[f"Liste {source} tronquée : taxons inférieurs non comparés."]
        )
    if article_names is None:
        return DiagnosticSousTaxons(
            limites=["Liste des taxons inférieurs non identifiée dans l'article : non comparée."]
        )
    dans_source = _distincts(source_names)
    if not dans_source:
        return DiagnosticSousTaxons()
    dans_article = _distincts(article_names)

    manquants_article = [n for n in dans_source if n not in dans_article]
    manquants_source = [n for n in dans_article if n not in dans_source]
    ecarts: list[Ecart] = []
    if manquants_article:
        liste = ", ".join(manquants_article)
        ecarts.append(
            Ecart(
                type="sous_taxon_absent_article",
                severite="info",
                propriete=_PROPRIETE,
                valeur_source=liste,
                source=source,
                message=(
                    f"{len(manquants_article)} taxon(s) de {source} absent(s) de la liste de "
                    f"l'article : {liste}."
                ),
            )
        )
    if manquants_source:
        liste = ", ".join(manquants_source)
        ecarts.append(
            Ecart(
                type="sous_taxon_absent_source",
                severite="info",
                propriete=_PROPRIETE,
                valeur_wikidata=liste,
                source=source,
                message=(
                    f"{len(manquants_source)} taxon(s) de l'article absent(s) de {source} : "
                    f"{liste}."
                ),
            )
        )
    comptes = ComptesSousTaxons(
        n_article=len(dans_article),
        n_source=len(dans_source),
        absents_article=manquants_article,
        absents_source=manquants_source,
    )
    return DiagnosticSousTaxons(ecarts=ecarts, comptes=comptes)


def diagnose_subtaxa(
    article_names: Sequence[str] | None,
    source_names: Sequence[str],
    *,
    source: str,
    truncated: bool,
) -> list[Ecart]:
    """Return only the findings of `compare_subtaxa`."""
    return compare_subtaxa(article_names, source_names, source=source, truncated=truncated).ecarts
