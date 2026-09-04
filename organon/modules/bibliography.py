"""Résolution partagée d'un DOI déjà repéré vers une citation wikitexte structurée : Wikidata
(P356) en priorité, pour produire `{{Bibliographie|Qxxx}}` quand l'ouvrage/article y est déjà
répertorié ; sinon Crossref, pour construire `{{Article}}`/`{{Ouvrage}}` à la main selon
`message["type"]`.

Partagé par tout module capable de repérer un DOI dans ses propres données — WoRMS (DOI scrapé
depuis la page de détail Aphia) et LPSN (DOI structuré, champ `publication_doi`) à ce jour : la
résolution DOI -> citation est identique une fois le DOI en main, seule la façon de le repérer
diffère d'un module à l'autre et reste dans le module correspondant (`wrms/citations.py`,
`lpsn/citations.py`)."""

from __future__ import annotations

import re

import httpx

from organon.core.http import USER_AGENT
from organon.modules.common import sparql_escape

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
CROSSREF_URL = "https://api.crossref.org/works"

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)

# Ce que les appelants (`*/citations.py::build_citation`) attrapent pour retomber sur leur texte
# brut : n'importe quelle étape réseau/JSON ci-dessous peut échouer sans que ce soit une erreur
# du module appelant.
LOOKUP_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError)

# Title/type identifiant un livre côté Crossref (voir `message["type"]`) — un article resterait
# construit via {{Article}} plutôt que mal étiqueté {{Ouvrage}}.
_CROSSREF_BOOK_TYPES = {"book", "monograph", "edited-book", "reference-book"}


async def _wikidata_qid_for_doi(client: httpx.AsyncClient, doi: str) -> str | None:
    """Cherche l'item Wikidata portant ce DOI (P356). Comparaison insensible à la casse via
    `UCASE` plutôt qu'une égalité stricte : Wikidata normalise les valeurs P356 en majuscules
    par convention, mais ce n'est pas garanti pour toutes les entrées."""
    query = (
        'SELECT ?item WHERE { ?item wdt:P356 ?doi . FILTER(UCASE(STR(?doi)) = UCASE("%s")) }'
        % sparql_escape(doi)
    )
    resp = await client.get(
        WIKIDATA_SPARQL_URL,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    if not bindings:
        return None
    return bindings[0]["item"]["value"].rsplit("/", 1)[-1]


async def _crossref_work(client: httpx.AsyncClient, doi: str) -> dict | None:
    resp = await client.get(f"{CROSSREF_URL}/{doi}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("message")


def build_template(nom: str, champs: list[tuple[str, str]], obligatoires: set[str]) -> str | None:
    """Construit `{{nom | ...}}` à partir des champs non vides, ou `None` si l'un des paramètres
    listés dans `obligatoires` (voir Modèle:Article/Modèle:Ouvrage sur frwiki — `titre` seul pour
    Ouvrage ; `titre`/`périodique`/`date` pour Article) manque : mieux vaut renoncer à
    l'enrichissement que produire une citation qui s'afficherait cassée sur l'article. Public :
    réutilisé par `wrms/citations.py::_via_bhl` pour le même modèle `{{Ouvrage}}` construit à la
    main depuis des métadonnées BHL plutôt que Crossref."""
    presents = {cle for cle, valeur in champs if valeur}
    if not obligatoires <= presents:
        return None
    parametres = " | ".join(f"{cle}={valeur}" for cle, valeur in champs if valeur)
    return f"{{{{{nom} | {parametres}}}}}"


def _crossref_authors(message: dict) -> list[str]:
    return [
        " ".join(part for part in (auteur.get("given"), auteur.get("family")) if part)
        for auteur in message.get("author", [])
        if auteur.get("family")
    ]


def _crossref_year(message: dict) -> str:
    for cle in ("published-print", "published", "issued"):
        parts = message.get(cle, {}).get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return ""


def _build_article_from_crossref(doi: str, message: dict) -> str | None:
    champs = [(f"auteur{i}", a) for i, a in enumerate(_crossref_authors(message), start=1)]
    champs += [
        ("titre", (message.get("title") or [""])[0]),
        ("périodique", (message.get("container-title") or [""])[0]),
        ("volume", message.get("volume", "")),
        ("numéro", message.get("issue", "")),
        ("date", _crossref_year(message)),
        ("pages", message.get("page", "")),
        ("doi", doi),
    ]
    return build_template("Article", champs, {"titre", "périodique", "date"})


def _build_ouvrage_from_crossref(doi: str, message: dict) -> str | None:
    champs = [(f"auteur{i}", a) for i, a in enumerate(_crossref_authors(message), start=1)]
    champs += [
        ("titre", (message.get("title") or [""])[0]),
        ("éditeur", message.get("publisher", "")),
        ("année", _crossref_year(message)),
    ]
    return build_template("Ouvrage", champs, {"titre"})


async def resolve_doi_citation(client: httpx.AsyncClient, doi: str) -> str | None:
    """Résout un DOI déjà repéré vers une citation wikitexte : Wikidata (P356) d'abord pour
    `{{Bibliographie|Qxxx}}`, sinon Crossref pour `{{Article}}`/`{{Ouvrage}}` (selon
    `message["type"]`). Renvoie `None` si ni l'une ni l'autre n'aboutit (DOI absent des deux
    sources, ou métadonnées Crossref insuffisantes pour les paramètres obligatoires du modèle) —
    à l'appelant de décider du repli (texte brut, autre méthode)."""
    qid = await _wikidata_qid_for_doi(client, doi)
    if qid:
        return f"{{{{Bibliographie|{qid}}}}}"
    message = await _crossref_work(client, doi)
    if not message:
        return None
    if message.get("type") in _CROSSREF_BOOK_TYPES:
        return _build_ouvrage_from_crossref(doi, message)
    return _build_article_from_crossref(doi, message)
