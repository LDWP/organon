"""Couche d'accès réseau pour la suggestion d'images Wikimedia Commons dans la taxobox : appels
HTTP et décodage JSON bruts uniquement (voir `organon.modules.commons_images.service` pour le
filtrage par licence/distinction qualité).

N'est volontairement pas un `TaxonomyModule` (voir `organon.core.registry`) : il ne participe ni
à la classification ni à l'enrichissement de la taxobox, il répond à une requête explicite de
l'utilisateur (choix d'une image) exposée par sa propre route (voir
`organon.api.routes.commons_images`), pas au pipeline `/generate`.

Le champ `extmetadata.Assessments` (renvoyé par `prop=imageinfo`) porte directement, pour un
fichier donné, la liste de ses distinctions Commons séparées par « | » (`quality`, `featured`,
`potd`...) — vérifié en direct sur l'API (ex. File:Atlantic cod live.jpg → Assessments vide ; un
Featured Picture → "quality|featured|potd"). Une image « remarquable » se détecte donc sur ce
champ, sans avoir à recouper la liste de `Category:Quality_images`/
`Category:Featured_pictures_on_Wikimedia_Commons` (des centaines de milliers de membres chacune,
impraticables à énumérer côté client pour une intersection)."""

from __future__ import annotations

from urllib.parse import unquote

import httpx

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "Organon/0.1 (https://fr.wikipedia.org/wiki/Projet:Biologie/Taxobot)"

# Limite de titres par appel `prop=imageinfo` côté anonyme (voir
# https://www.mediawiki.org/wiki/API:Query#Multiple_values, "500" pour les comptes autorisés,
# "50" sinon — ce client n'authentifie jamais ses requêtes).
_IMAGEINFO_BATCH_SIZE = 50


class CommonsImagesAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT})
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def category_files(self, category_title: str, *, limit: int = 500) -> list[str]:
        """Titres des fichiers membres d'une catégorie Commons (ex. `Category:Gadus morhua`),
        jusqu'à `limit` résultats en une seule page. Fonctionne même si la page de catégorie
        elle-même n'a jamais été créée (catégorie "rouge") : l'appartenance d'un fichier à une
        catégorie ne dépend que de son wikitexte, pas de l'existence de la page de catégorie."""
        resp = await self._client.get(
            COMMONS_API_URL,
            params={
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmtype": "file",
                "cmlimit": min(limit, 500),
                "format": "json",
            },
        )
        resp.raise_for_status()
        members = resp.json().get("query", {}).get("categorymembers", [])
        return [m["title"] for m in members]

    async def imageinfo(self, titles: list[str]) -> dict[str, dict]:
        """URL de vignette et métadonnées (licence, distinctions) pour une liste de titres de
        fichiers, par lots de `_IMAGEINFO_BATCH_SIZE` titres."""
        result: dict[str, dict] = {}
        for i in range(0, len(titles), _IMAGEINFO_BATCH_SIZE):
            batch = titles[i : i + _IMAGEINFO_BATCH_SIZE]
            resp = await self._client.get(
                COMMONS_API_URL,
                params={
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 320,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                title = page.get("title")
                infos = page.get("imageinfo")
                if title and infos:
                    result[title] = infos[0]
        return result

    async def wikidata_image(self, taxon: str) -> str | None:
        """Nom de fichier Commons (propriété P18) déjà utilisé par l'item Wikidata de ce taxon,
        s'il existe — sert uniquement à repérer qu'une suggestion n'est pas une nouveauté (voir
        `organon.modules.commons_images.service`), jamais à la construire elle-même."""
        escaped = taxon.replace('"', '\\"')
        query = (
            "SELECT ?image WHERE { "
            f'?item wdt:P31 wd:Q16521 ; wdt:P225 "{escaped}" ; wdt:P18 ?image . '
            "}"
        )
        resp = await self._client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        # Valeur du type "http://commons.wikimedia.org/wiki/Special:FilePath/Atlantic%20cod.jpg"
        # (vérifié en direct) : le nom de fichier est le dernier segment, encodé en pourcent.
        uri = bindings[0]["image"]["value"]
        return unquote(uri.rsplit("/", 1)[-1])
