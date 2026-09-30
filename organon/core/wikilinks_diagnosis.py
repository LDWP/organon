"""Pure comparison of an article's external links with the generator's.

Findings (`Ecart`) only, never a corrected value. The expected text
is reparsed with the article parser, so no template-to-module
table is needed. Links only in the article are never reported.
"""

from __future__ import annotations

from organon.core.update_diagnosis import Ecart, Severite
from organon.core.wikilinks_parser import (
    parse_autres_projets,
    parse_bases,
    parse_categorie_principale,
)

_PROPRIETE_PROJETS = "Autres projets"
_PROPRIETE_CATEGORIE = "catégorie principale"
# The generic template has no id as first argument.
_MODELES_IGNORES = {"lien web"}


def _norm(valeur: str) -> str:
    """Normalize underscores and surrounding whitespace."""
    return valeur.replace("_", " ").strip()


def diagnose_liens(article: str, attendu: str, *, source: str) -> list[Ecart]:
    """Compare external links of `article` with `attendu`.

    `attendu` is the output of `render_see_also`. `valeur_wikidata`
    holds the article value, `valeur_source` the generator's.
    `commons*` parameters compare by value across all Commons targets;
    a value known under another parameter yields at most
    `projet_absent_article`.
    """

    def ecart(
        type_: str,
        severite: Severite,
        propriete: str,
        message: str,
        valeur_article: str | None,
        valeur_source: str | None,
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

    ecarts: list[Ecart] = []

    projets_article = parse_autres_projets(article)
    projets_attendus = parse_autres_projets(attendu)
    commons_article = {_norm(v) for k, v in projets_article.items() if k.startswith("commons")}
    commons_attendus = {_norm(v) for k, v in projets_attendus.items() if k.startswith("commons")}
    for projet, cible in sorted(projets_attendus.items()):
        en_article = projets_article.get(projet)
        if projet.startswith("commons"):
            if _norm(cible) in commons_article:
                continue
            if en_article is not None and _norm(en_article) in commons_attendus:
                en_article = None
        if en_article is None:
            ecarts.append(
                ecart(
                    "projet_absent_article",
                    "info",
                    _PROPRIETE_PROJETS,
                    f"Le lien vers {projet} ({cible}) est absent de l'article.",
                    None,
                    cible,
                )
            )
        elif _norm(en_article) != _norm(cible):
            ecarts.append(
                ecart(
                    "projet_different",
                    "avertissement",
                    _PROPRIETE_PROJETS,
                    f"Le lien vers {projet} diffère : {en_article} dans l'article, "
                    f"{cible} dans la source.",
                    en_article,
                    cible,
                )
            )

    if parse_categorie_principale(attendu) and parse_categorie_principale(article) is None:
        ecarts.append(
            ecart(
                "categorie_principale_absente",
                "info",
                _PROPRIETE_CATEGORIE,
                "Le modèle {{catégorie principale}} est absent de l'article.",
                None,
                None,
            )
        )

    bases_article: dict[str, set[str]] = {}
    for modele, arg in parse_bases(article):
        bases_article.setdefault(modele, set()).add(_norm(arg))
    vues: set[tuple[str, str]] = set()
    for modele, arg in parse_bases(attendu):
        if modele in _MODELES_IGNORES or (modele, arg) in vues:
            continue
        vues.add((modele, arg))
        ids_article = bases_article.get(modele)
        nom = modele.upper() if modele.isascii() and " " not in modele else modele
        if ids_article is None:
            ecarts.append(
                ecart(
                    "base_absente_article",
                    "info",
                    nom,
                    f"La base {nom} ({arg}) est absente de la section liens externes.",
                    None,
                    arg,
                )
            )
        elif _norm(arg) not in ids_article:
            valeur = ", ".join(sorted(ids_article))
            ecarts.append(
                ecart(
                    "base_identifiant_different",
                    "avertissement",
                    nom,
                    f"{nom} : identifiant {valeur} dans l'article, {arg} dans la source.",
                    valeur,
                    arg,
                )
            )
    return ecarts
