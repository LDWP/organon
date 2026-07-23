"""Couche d'accès réseau pour Animal Diversity Web (animaldiversity.org) : scraping HTML sans
API, une page potentielle par taxon (`accounts/<Nom_avec_underscores>/`). L'auteur/l'année ne
sont exposés nulle part sous forme structurée : seul le paragraphe "To cite this page:" en
donne une version textuelle, extraite ici par expression régulière (1/2/3+ auteurs).

Vérifié en direct (2026-07-23), deux écarts avec le PHP d'origine :

- Le marqueur "taxon non trouvé" du PHP (`: Not Found<`) n'existe plus : la page 404 actuelle
  répond en HTTP 200 avec un simple `<h1>Page not found</h1>` dans le corps — détecté à la
  place. Certains taxons valides (ex. *Bufo bufo*) redirigent (302) leur compte vers une
  sous-page "classification" sans texte de citation propre ; `follow_redirects=True` permet de
  quand même reconnaître ces taxons comme trouvés (juste sans citation).
- Le HTML a changé de structure : la citation est coupée par une balise `<span>` imbriquée
  portant la date de consultation, que le site ne rend d'ailleurs jamais lui-même (littéralement
  `{%B %d, %Y}` non substitué) — ignorée ici, seule l'année de publication (dans le texte de la
  citation elle-même) est retenue.

Bug corrigé plutôt que reproduit : la regex PHP des auteurs suivants, appliquée à la citation
entière, capture parfois "and" comme un nom d'auteur bidon quand le premier auteur n'est pas
suivi d'une virgule avant "and" (ex. "Wund, M. and P. Myers 2005." sur la fiche Mammalia,
observé en direct) — gonflant artificiellement le décompte d'auteurs. Ici, la recherche des
auteurs suivants est bornée au texte *après* le premier auteur trouvé, ce qui élimine le faux
positif sans changer le résultat sur les citations bien formées (ex. "Myers, P., R. Espinosa,
C. S. Parr, ..., and T. A. Dewey.")."""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

import httpx

BASE_URL = "https://animaldiversity.org"

_NOT_FOUND_RE = re.compile(r"<h1>\s*Page not found\s*</h1>")
_CITATION_BLOCK_RE = re.compile(
    r'To cite this page:(?P<texte>.*?)<span[^>]*data-slot="accessed-date"', re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")

_LETTERS = r"[^\W\d_]+"
_FIRST_AUTHOR_RE = re.compile(
    rf"(?P<nom>{_LETTERS}),\s(?P<prenom1>[A-Z]\.)(?P<prenom2> [A-Z]\.)?"
)
_OTHER_AUTHOR_RE = re.compile(
    rf"(and )?(?P<prenom1>[A-Z]\.)(?P<prenom2> [A-Z]\.)? (?P<nom>{_LETTERS})"
)
_YEAR_RE = re.compile(r"([1-9][0-9]{3})[.]")


@dataclass
class Author:
    nom: str
    prenom1: str
    prenom2: str | None = None


@dataclass
class AdwCitation:
    """Citation extraite de la page ADW d'un taxon. `premier_auteur` vaut `None` quand la page
    existe mais ne porte aucune citation exploitable (ex. fiche "classification" seule)."""

    premier_auteur: Author | None
    autres_auteurs: list[Author] = field(default_factory=list)
    annee: str | None = None


def _parse_author(match: re.Match[str]) -> Author:
    return Author(
        nom=match.group("nom"),
        prenom1=match.group("prenom1"),
        prenom2=(match.group("prenom2") or "").strip() or None,
    )


def _parse_citation(html_page: str) -> AdwCitation:
    block = _CITATION_BLOCK_RE.search(html_page)
    if block is None:
        return AdwCitation(premier_auteur=None)

    texte = _TAG_RE.sub(" ", block.group("texte"))
    texte = _html.unescape(" ".join(texte.split()))

    premier_match = _FIRST_AUTHOR_RE.search(texte)
    if premier_match is None:
        return AdwCitation(premier_auteur=None)

    reste = texte[premier_match.end() :]
    autres = [_parse_author(m) for m in _OTHER_AUTHOR_RE.finditer(reste)]

    annee_match = _YEAR_RE.search(texte)

    return AdwCitation(
        premier_auteur=_parse_author(premier_match),
        autres_auteurs=autres,
        annee=annee_match.group(1) if annee_match else None,
    )


class AdwAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, slug: str) -> AdwCitation | None:
        """Renvoie la citation du taxon `slug` (espaces déjà remplacés par des underscores), ou
        `None` si le taxon n'existe pas sur ADW. Une `AdwCitation` dont `premier_auteur` vaut
        `None` signifie que la page existe mais n'a pas de citation propre à en tirer."""
        resp = await self._client.get(f"{BASE_URL}/accounts/{slug}/")
        if resp.status_code >= 400:
            return None
        if _NOT_FOUND_RE.search(resp.text):
            return None
        return _parse_citation(resp.text)
