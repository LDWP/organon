"""Network access for Commons image suggestions: raw HTTP and JSON.

See `organon.modules.commons_images.service` for the filtering by
license and quality distinction.

Deliberately not a `TaxonomyModule`: it takes part in neither the
classification nor the taxobox enrichment. It answers an explicit user
request (choosing an image) through its own route (see
`organon.api.routes.commons_images`), not the `/generate` pipeline.

`extmetadata.Assessments` (from `prop=imageinfo`) lists a file's Commons
distinctions separated by "|" (`quality`, `featured`, `potd`…), so a
notable image is detected on that field alone, without intersecting the
huge `Category:Quality_images` and
`Category:Featured_pictures_on_Wikimedia_Commons`.
"""

from __future__ import annotations

import logging
from urllib.parse import unquote

import httpx

from organon.core.http import USER_AGENT, OwnedClientMixin
from organon.modules.common import sparql_escape

logger = logging.getLogger(__name__)

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Title limit per anonymous `prop=imageinfo` call (500 for authorized
# accounts, 50 otherwise; this client never authenticates).
_IMAGEINFO_BATCH_SIZE = 50


class CommonsImagesAdapter(OwnedClientMixin):
    """Raw Commons image API client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, headers={"User-Agent": USER_AGENT})

    async def category_files(self, category_title: str, *, limit: int = 500) -> list[str]:
        """Return the titles of the files of a Commons category.

        Up to `limit` results in one page. Works even if the category
        page was never created: membership depends on the file's
        wikitext only.
        """
        try:
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
        except httpx.HTTPError as exc:
            logger.warning("Commons : catégorie « %s » illisible (%s)", category_title, exc)
            return []
        members = resp.json().get("query", {}).get("categorymembers", [])
        return [m["title"] for m in members]

    async def imageinfo(self, titles: list[str]) -> dict[str, dict]:
        """Return thumbnail URL and metadata per file title.

        License and distinctions, in batches of `_IMAGEINFO_BATCH_SIZE`.
        """
        result: dict[str, dict] = {}
        for i in range(0, len(titles), _IMAGEINFO_BATCH_SIZE):
            batch = titles[i : i + _IMAGEINFO_BATCH_SIZE]
            try:
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
            except httpx.HTTPError as exc:
                logger.warning("Commons : métadonnées d'images illisibles (%s)", exc)
                continue
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                title = page.get("title")
                infos = page.get("imageinfo")
                if title and infos:
                    result[title] = infos[0]
        return result

    async def wikidata_image(self, taxon: str) -> str | None:
        """Return the Commons file (P18) the taxon's Wikidata item uses.

        Only to flag a suggestion as not new (see `service`), never to
        build one.
        """
        escaped = sparql_escape(taxon)
        query = (
            "SELECT ?image WHERE { "
            f'?item wdt:P31 wd:Q16521 ; wdt:P225 "{escaped}" ; wdt:P18 ?image . '
            "}"
        )
        try:
            resp = await self._client.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Wikidata : image P18 de « %s » illisible (%s)", taxon, exc)
            return None
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        # The value is a Special:FilePath URL: the file name is its last
        # segment, percent-encoded.
        uri = bindings[0]["image"]["value"]
        return unquote(uri.rsplit("/", 1)[-1])
