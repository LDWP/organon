"""Enrichissement de la « publication originale » WoRMS (`struct.originale`, voir
`organon.modules.wrms.adapter.WrmsAdapter.original_description`) : quand un DOI est repérable
dans le texte scrapé, délègue à `organon.modules.bibliography.resolve_doi_citation` (Wikidata
P356 -> `{{Bibliographie|Qxxx}}`, sinon Crossref -> `{{Article}}`/`{{Ouvrage}}`, partagé avec
LPSN). À défaut de DOI, un lien biodiversitylibrary.org dans le texte déclenche le même
enrichissement via l'API BHL — seule façon d'obtenir un titre/auteurs/éditeur structurés sur
cette plateforme, le texte WoRMS environnant restant une prose libre trop peu fiable à parser
(annotations entre crochets, dates de publication fragmentées). La notice BHL porte parfois
elle-même un identifiant Wikidata (`Title.Identifiers`) : quand c'est le cas et que l'item est
bien une édition (P31=Q3331189, pas l'œuvre générique), `{{Bibliographie}}` prend le pas sur la
construction manuelle de `{{Ouvrage}}` — vérifié en direct sur Linnaeus 1758 (BHL TitleID 542 ->
Q4547210).

Toute étape en échec (réseau, forme de réponse inattendue, clé BHL absente, genre BHL non pris
en charge) retombe sur le texte brut déjà produit aujourd'hui : cet enrichissement est un bonus,
jamais une condition de succès du module WoRMS."""

from __future__ import annotations

import re

from organon.modules.bibliography import DOI_RE, LOOKUP_ERRORS, build_template
from organon.modules.wrms.adapter import WrmsAdapter

_BHL_URL_RE = re.compile(r"https?://(?:www\.)?biodiversitylibrary\.org/page/(\d+)[^\s\"'<>]*")
_QID_RE = re.compile(r"^Q[1-9]\d*$")

# Title/Genre BHL identifiant un livre (voir doc API v3, "Data Elements") — un article/numéro de
# série resterait en texte brut plutôt que d'être mal étiqueté {{Ouvrage}}.
_BHL_BOOK_GENRES = {"Monograph/Item", "Collection"}


def _extract_doi(text: str) -> str | None:
    match = DOI_RE.search(text)
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
    return build_template("Ouvrage", champs, {"titre"})


async def build_citation(adapter: WrmsAdapter, raw_text: str | None) -> str | None:
    if not raw_text:
        return raw_text
    try:
        doi = _extract_doi(raw_text)
        if doi:
            enrichie = await adapter.resolve_doi_citation(doi)
            if enrichie:
                return enrichie
        bhl_match = _BHL_URL_RE.search(raw_text)
        if bhl_match:
            enrichie = await _via_bhl(adapter, bhl_match.group(0), bhl_match.group(1))
            if enrichie:
                return enrichie
    except LOOKUP_ERRORS:
        pass
    return raw_text
