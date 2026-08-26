"""Enrichissement de la « publication originale » WoRMS (`struct.originale`, voir
`organon.modules.wrms.adapter.WrmsAdapter.original_description`) : quand un DOI est repérable
dans le texte scrapé, recherche l'item Wikidata correspondant (P356) pour produire
`{{Bibliographie|Qxxx}}`, sinon interroge Crossref pour construire `{{Article}}`/`{{Ouvrage}}` à
la main (selon `message.type`). À défaut de DOI, un lien biodiversitylibrary.org dans le texte
déclenche le même enrichissement via l'API BHL — seule façon d'obtenir un titre/auteurs/éditeur
structurés sur cette plateforme, le texte WoRMS environnant restant une prose libre trop peu
fiable à parser (annotations entre crochets, dates de publication fragmentées). La notice BHL
porte parfois elle-même un identifiant Wikidata (`Title.Identifiers`) : quand c'est le cas et que
l'item est bien une édition (P31=Q3331189, pas l'œuvre générique), `{{Bibliographie}}` prend le
pas sur la construction manuelle de `{{Ouvrage}}` — vérifié en direct sur Linnaeus 1758 (BHL
TitleID 542 -> Q4547210).

Toute étape en échec (réseau, forme de réponse inattendue, clé BHL absente, genre BHL non pris
en charge) retombe sur le texte brut déjà produit aujourd'hui : cet enrichissement est un bonus,
jamais une condition de succès du module WoRMS."""

from __future__ import annotations

import re

import httpx

from organon.modules.wrms.adapter import WrmsAdapter

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
_BHL_URL_RE = re.compile(r"https?://(?:www\.)?biodiversitylibrary\.org/page/(\d+)[^\s\"'<>]*")
_QID_RE = re.compile(r"^Q[1-9]\d*$")

# Ce que build_citation() attrape pour retomber sur le texte brut : n'importe quelle étape
# réseau/JSON peut échouer sans que ce soit une erreur du module WoRMS lui-même.
_LOOKUP_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError)

# Title/Genre BHL identifiant un livre (voir doc API v3, "Data Elements") — un article/numéro de
# série resterait en texte brut plutôt que d'être mal étiqueté {{Ouvrage}}.
_BHL_BOOK_GENRES = {"Monograph/Item", "Collection"}
_CROSSREF_BOOK_TYPES = {"book", "monograph", "edited-book", "reference-book"}


def _extract_doi(text: str) -> str | None:
    match = _DOI_RE.search(text)
    if match is None:
        return None
    # La prose environnante ("... 10.1234/abc.). Disponible ...") capture parfois un signe de
    # ponctuation final qui ne fait pas partie du DOI.
    return match.group(0).rstrip(".,;)]")


def _bhl_wikidata_qid(title: dict) -> str | None:
    for identifiant in title.get("Identifiers", []):
        if identifiant.get("IdentifierName") == "Wikidata":
            valeur = identifiant.get("IdentifierValue", "")
            if _QID_RE.match(valeur):
                return valeur
    return None


def _build_template(nom: str, champs: list[tuple[str, str]], obligatoires: set[str]) -> str | None:
    """Construit `{{nom | ...}}` à partir des champs non vides, ou `None` si l'un des paramètres
    listés dans `obligatoires` (voir Modèle:Article/Modèle:Ouvrage sur frwiki — `titre` seul pour
    Ouvrage ; `titre`/`périodique`/`date` pour Article) manque : mieux vaut renoncer à
    l'enrichissement que produire une citation qui s'afficherait cassée sur l'article."""
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
    return _build_template("Article", champs, {"titre", "périodique", "date"})


def _build_ouvrage_from_crossref(doi: str, message: dict) -> str | None:
    champs = [(f"auteur{i}", a) for i, a in enumerate(_crossref_authors(message), start=1)]
    champs += [
        ("titre", (message.get("title") or [""])[0]),
        ("éditeur", message.get("publisher", "")),
        ("année", _crossref_year(message)),
    ]
    return _build_template("Ouvrage", champs, {"titre"})


async def _via_doi(adapter: WrmsAdapter, doi: str) -> str | None:
    qid = await adapter.wikidata_qid_for_doi(doi)
    if qid:
        return f"{{{{Bibliographie|{qid}}}}}"
    message = await adapter.crossref_work(doi)
    if not message:
        return None
    if message.get("type") in _CROSSREF_BOOK_TYPES:
        return _build_ouvrage_from_crossref(doi, message)
    return _build_article_from_crossref(doi, message)


async def _via_bhl(adapter: WrmsAdapter, page_url: str, page_id: str) -> str | None:
    page = await adapter.bhl_page_metadata(page_id)
    if not page:
        return None
    item = await adapter.bhl_item_metadata(page["ItemID"])
    if not item:
        return None
    title = await adapter.bhl_title_metadata(item["TitleID"])
    if not title or title.get("Genre") not in _BHL_BOOK_GENRES:
        return None
    qid = _bhl_wikidata_qid(title)
    if qid and await adapter.wikidata_is_edition(qid):
        return f"{{{{Bibliographie|{qid}}}}}"
    auteurs = enumerate((a for a in title.get("Authors", []) if a.get("Name")), start=1)
    champs = [(f"auteur{i}", a["Name"]) for i, a in auteurs]
    champs += [
        ("titre", title.get("FullTitle") or title.get("ShortTitle", "")),
        ("lieu", title.get("PublisherPlace", "")),
        ("éditeur", title.get("PublisherName", "")),
        ("année", str(item.get("Year") or title.get("PublicationDate", ""))),
        ("lire en ligne", page_url),
    ]
    return _build_template("Ouvrage", champs, {"titre"})


async def build_citation(adapter: WrmsAdapter, raw_text: str | None) -> str | None:
    if not raw_text:
        return raw_text
    try:
        doi = _extract_doi(raw_text)
        if doi:
            enrichie = await _via_doi(adapter, doi)
            if enrichie:
                return enrichie
        bhl_match = _BHL_URL_RE.search(raw_text)
        if bhl_match:
            enrichie = await _via_bhl(adapter, bhl_match.group(0), bhl_match.group(1))
            if enrichie:
                return enrichie
    except _LOOKUP_ERRORS:
        pass
    return raw_text
