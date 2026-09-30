"""Pure parser of the sub-taxa list of a frwiki article.

Lists live in `{{Taxobox taxons}}` or in bullets under a section
whose title contains a keyword, possibly inside `{{colonnes}}`.
Nothing outside these zones is read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from organon.core.taxobox_parser import _split_args, _templates

_MOTS_ZONE = ("taxons", "espèces", "genres", "liste des")
_TITRE_RE = re.compile(r"^(={2,6})\s*(.*?)\s*=+\s*$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_REF_RE = re.compile(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_SMALL_RE = re.compile(r"<small>.*?</small>", re.DOTALL | re.IGNORECASE)
# `{{colonnes|…|` opens on its own line: keep only the bullets.
_COLONNES_RE = re.compile(r"\{\{\s*colonnes\s*\|[^{}\n]*\n", re.IGNORECASE)
_MODELE_LIGNE_RE = re.compile(r"\{\{[^{}\n]*\}\}")
_RANG_RE = re.compile(
    r"^(?:(?:super|sous|infra|micro|épi)-?)?"
    r"(?:domaine|règne|embranchement|phylum|division|classe|ordre|famille|tribu|genre|espèce"
    r"|section|série|variété|forme|clade|cohorte|légion)s?\b\s*:?\s*",
    re.IGNORECASE,
)
_LIEN_RE = re.compile(r"(?P<it>'')?\s*\[\[(?P<cible>[^\]|]+)(?:\|(?P<lib>[^\]]*))?\]\]")
_ITALIQUE_RE = re.compile(r"''\s*(?P<nom>[^'\[\]{}]+?)\s*''")
_DESAMBIG_RE = re.compile(r"\s*\([^)]*\)$")
_ABREVIATION_RE = re.compile(r"^[A-ZÀ-Ý]\.\s")


@dataclass(frozen=True)
class SousTaxonsView:
    """Latin names of the sub-taxa found."""

    noms: list[str] = field(default_factory=list)


def _sans_modeles(text: str) -> str:
    """Strip nested multiline `{{ }}` templates."""
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}" and depth > 0:
            depth -= 1
            i += 2
        else:
            if depth == 0:
                out.append(text[i])
            i += 1
    return "".join(out)


def _nom_item(ligne: str) -> str | None:
    """Return the latin name of a bullet line, or None."""
    while (nouvelle := _MODELE_LIGNE_RE.sub("", ligne)) != ligne:
        ligne = nouvelle
    if not ligne.startswith("*"):
        return None
    reste = ligne.lstrip("*").replace("'''", "").replace("&nbsp;", " ").strip()
    reste = reste.lstrip("†").strip()
    reste = _RANG_RE.sub("", reste, count=1).lstrip("†").strip()

    lien = _LIEN_RE.match(reste)
    if lien:
        cible, libelle = lien.group("cible").strip(), lien.group("lib")
        if libelle is not None and (lien.group("it") or "''" in libelle):
            nom = libelle.replace("''", "").strip()
        else:
            nom = _DESAMBIG_RE.sub("", cible)
        suite = reste[lien.end() :]
    else:
        italique = _ITALIQUE_RE.match(reste)
        if italique is None:
            return None
        nom = italique.group("nom")
        suite = reste[italique.end() :]

    # "''Name''?" is a doubtful taxon, not listed.
    if suite.lstrip("'").startswith("?"):
        return None
    if not nom or ":" in nom or _ABREVIATION_RE.match(nom):
        return None
    if not (nom[0].isupper() or nom[0] == "×"):
        return None
    return " ".join(nom.split())


def _noms(lignes: list[str], vus: dict[str, None]) -> None:
    """Add the names of `lignes` to the ordered set `vus`."""
    for ligne in lignes:
        nom = _nom_item(ligne)
        if nom:
            vus.setdefault(nom)


def parse_sous_taxons(wikitext: str) -> SousTaxonsView | None:
    """Parse the sub-taxa names of `wikitext`.

    None if no list zone is found, as opposed to an empty zone
    (`noms == []`). There is no fallback outside the keywords.
    """
    texte = _COMMENT_RE.sub("", wikitext)
    texte = _REF_RE.sub("", texte)
    texte = _SMALL_RE.sub("", texte)
    texte = _COLONNES_RE.sub("\n", texte)

    vus: dict[str, None] = {}
    trouvee = False

    debut = re.search(r"\{\{\s*taxobox début", texte, re.IGNORECASE)
    if debut is not None:
        fin = re.search(r"\{\{\s*taxobox fin", texte[debut.start() :], re.IGNORECASE)
        bloc = texte[debut.start() : debut.start() + fin.end()] if fin else texte[debut.start() :]
        for corps in _templates(bloc):
            parts = _split_args(corps)
            if parts[0].strip().casefold() != "taxobox taxons":
                continue
            trouvee = True
            _noms(_sans_modeles("|".join(parts[2:])).splitlines(), vus)

    niveau_zone: int | None = None
    for ligne in texte.splitlines():
        titre = _TITRE_RE.match(ligne)
        if titre:
            niveau = len(titre.group(1))
            if niveau_zone is not None and niveau <= niveau_zone:
                niveau_zone = None
            if niveau_zone is None and any(m in titre.group(2).casefold() for m in _MOTS_ZONE):
                niveau_zone = niveau
                trouvee = True
        elif niveau_zone is not None:
            _noms([ligne], vus)

    return SousTaxonsView(list(vus)) if trouvee else None
