"""Pure comparison of an article's Taxobox with a source's ranks.

Findings (`Ecart`) only, never a corrected value. A source silent
on a rank is never an error (`taxobox_rang_absent_source` is
`info`).
"""

from __future__ import annotations

from organon.core.taxobox_parser import TaxoboxView
from organon.core.update_diagnosis import Ecart, Severite

_PROPRIETE_TAXON = "Taxobox taxon"
_PROPRIETE_CLASSIFICATION = "classification"
_PROPRIETE_UICN = "Taxobox UICN"


def diagnose_taxobox(
    view: TaxoboxView | None,
    *,
    rank_lines: list[tuple[str, str]],
    taxon_nom: str,
    taxon_rang: str | None,
    source: str,
    redirected_from: str | None = None,
) -> list[Ecart]:
    """Compare the article Taxobox with the source ranks.

    `rank_lines` are the source (rank, name) pairs; `source` is the
    Taxobox classification code compared with the article's
    `classification=`. `valeur_wikidata` holds the article value,
    `valeur_source` the source's.
    """

    def ecart(
        type_: str,
        severite: Severite,
        propriete: str,
        message: str,
        valeur_article: str | None = None,
        valeur_source: str | None = None,
    ) -> Ecart:
        return Ecart(
            type=type_,
            severite=severite,
            propriete=propriete,
            valeur_wikidata=valeur_article,
            valeur_source=valeur_source,
            source=source,
            message=message,
        )

    if view is None:
        return [
            ecart(
                "taxobox_absente",
                "avertissement",
                "Taxobox",
                "Aucune Taxobox exploitable dans l'article.",
            )
        ]

    ecarts: list[Ecart] = []

    if view.taxon is not None:
        nom_different = view.taxon.nom.casefold() != taxon_nom.casefold()
        if nom_different and redirected_from is not None:
            return [
                ecart(
                    "taxobox_taxon_different",
                    "erreur",
                    _PROPRIETE_TAXON,
                    f"{source} traite « {redirected_from} » comme synonyme de « {taxon_nom} ».",
                    view.taxon.nom,
                    taxon_nom,
                )
            ]  # ranks would describe the accepted taxon, not this article
        if nom_different:
            ecarts.append(
                ecart(
                    "taxobox_taxon_different",
                    "erreur",
                    _PROPRIETE_TAXON,
                    "Nom du taxon différent.",
                    view.taxon.nom,
                    taxon_nom,
                )
            )
        if taxon_rang is not None and view.taxon.rang != taxon_rang:
            ecarts.append(
                ecart(
                    "taxobox_taxon_different",
                    "erreur",
                    _PROPRIETE_TAXON,
                    "Rang du taxon différent.",
                    view.taxon.rang,
                    taxon_rang,
                )
            )

    article: dict[str, str | None] = {}
    for r in view.rangs:
        article.setdefault(r.rang, r.nom)
    reference = dict(reversed(rank_lines))  # first duplicate wins

    for rang, nom_source in rank_lines:
        if rang not in article:
            ecarts.append(
                ecart(
                    "taxobox_rang_absent_article",
                    "info",
                    rang,
                    "Rang absent de la Taxobox.",
                    None,
                    nom_source,
                )
            )
            continue
        nom_article = article[rang]
        if nom_article is not None and nom_article.casefold() != reference[rang].casefold():
            ecarts.append(
                ecart(
                    "taxobox_nom_different",
                    "erreur",
                    rang,
                    "Nom différent.",
                    nom_article,
                    reference[rang],
                )
            )

    for rang, nom_article in article.items():
        if rang not in reference:
            ecarts.append(
                ecart(
                    "taxobox_rang_absent_source",
                    "info",
                    rang,
                    "Rang absent de la source.",
                    nom_article,
                    None,
                )
            )

    if view.classification and view.classification.casefold() != source.casefold():
        ecarts.append(
            ecart(
                "taxobox_classification",
                "info",
                _PROPRIETE_CLASSIFICATION,
                "Classification déclarée différente de la source.",
                view.classification,
                source,
            )
        )
    return ecarts


def diagnose_uicn(
    view: TaxoboxView | None,
    *,
    risque: str | None,
    critere: str | None,
    source: str,
) -> list[Ecart]:
    """Compare the article's `Taxobox UICN` with the source status.

    A silent source yields nothing; criteria the source lacks are not
    compared.
    """
    if not risque:
        return []
    article = view.uicn if view is not None else None

    def ecart(type_: str, severite: Severite, message: str, valeur_article: str | None) -> Ecart:
        return Ecart(
            type=type_,
            severite=severite,
            propriete=_PROPRIETE_UICN,
            valeur_wikidata=valeur_article,
            valeur_source=_format_uicn(risque, critere),
            source=source,
            message=message,
        )

    if article is None:
        return [ecart("uicn_absent_article", "info", "Statut UICN absent de la Taxobox.", None)]
    if article.risque.casefold() != risque.casefold() or (
        critere and (article.critere or "").casefold() != critere.casefold()
    ):
        return [
            ecart(
                "uicn_different",
                "avertissement",
                "Statut UICN différent.",
                _format_uicn(article.risque, article.critere),
            )
        ]
    return []


def _format_uicn(risque: str, critere: str | None) -> str:
    """Format a risk code with optional criteria."""
    return f"{risque} {critere}" if critere else risque
