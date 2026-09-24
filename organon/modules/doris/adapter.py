"""Network access to DORIS (doris.ffessm.fr).

No public API (`/Especes/api` is a 404; see `db_inventory.yaml`, id:
doris), but a working HTML name search.

The site's search form POSTs `(name)=<query>` and
`DestinationURL=find/species` to `/content/action`, which redirects
(302, followed by httpx) to `/find/species/(name)/<query>`: a
relevance-ranked full-text search, not an exact server-side filter. The
exact filter on the scientific name is client-side, on the first page of
results only; in practice the exact match is always first.

The species page itself is not fetched (no author collected): its URL
needs a full slug (`/Especes/Genre-espece-Nom-commun-ID`; a bare ID is a
404), unlike the legacy `fiche2.asp?fiche_numero=ID`, kept as a
permanent redirect and used by `organon.modules.doris.module` for the
debug link.
"""

from __future__ import annotations

import re

import httpx

from organon.core.http import OwnedClientMixin

SEARCH_URL = "https://doris.ffessm.fr/content/action"
LEGACY_FICHE_URL = "https://doris.ffessm.fr/fiche2.asp"

_RESULT_RE = re.compile(
    r'<a href="https://doris\.ffessm\.fr/Especes/[^"]+-(?P<id>\d+)/\(rOffset\)/\d+">\s*'
    r"(?P<nom_commun>[^<]*)<br>\s*<em>(?P<nom_scientifique>[^<]+)</em>\s*</a>"
)


class DorisAdapter(OwnedClientMixin):
    """Raw DORIS client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, follow_redirects=True)

    async def search(self, found_name: str) -> tuple[str, str] | None:
        """Return (page id, common name) of the exact match, or None.

        The first result whose scientific name is exactly `found_name`.
        """
        resp = await self._client.post(
            SEARCH_URL, data={"DestinationURL": "find/species", "(name)": found_name}
        )
        resp.raise_for_status()
        for match in _RESULT_RE.finditer(resp.text):
            if match.group("nom_scientifique").strip() == found_name:
                return match.group("id"), match.group("nom_commun").strip()
        return None
