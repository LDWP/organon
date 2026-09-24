"""Network access to Tela Botanica / TelaMétro (BDTFX).

The BDTFX is the reference for the flora of metropolitan France. HTTP
calls go to the Algolia index `Flore` that the site itself uses for its
search, and the "Ethnobotanique" tab of the eFlore page is scraped for
the typed vernacular names. The `x-algolia-api-key` below is a
search-only key (read-only, public by construction, visible in the
site's client JavaScript), not a secret.

The vernacular names of the Algolia index (`bdtfx.common_name`) are a
flat list with no status or language, matching no coherent subset of the
full table. That table, with its "Conseil d'emploi" per name (Recommandé
ou typique, Secondaire ou régional, Peu usité et à éviter), is in no
documented JSON API: only the server-rendered HTML of the Ethnobotanique
tab exposes it (`<table class="liste_noms_vernaculaires">`), hence the
scraping.
"""

from __future__ import annotations

import html
import re

from organon.core.http import OwnedClientMixin

ALGOLIA_URL = "https://yotvbfebjc-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_PARAMS = {
    "x-algolia-agent": "Algolia for vanilla JavaScript (lite) 3.24.5",
    "x-algolia-application-id": "YOTVBFEBJC",
    "x-algolia-api-key": "843a36372facc0f1836f53d1d5968aa8",
}

ETHNOBOTANY_URL = "https://www.tela-botanica.org/eflore/"

_VERNACULAR_LINE_RE = re.compile(
    r"<tr>\s*<td>(?P<langue>[^<]*)</td>\s*<td>(?P<nom>[^<]*)</td>\s*<td>[^<]*</td>\s*"
    r"<td>(?P<statut>[^<]*)</td>\s*<td>[^<]*</td>\s*</tr>"
)
# "Peu usité et à éviter" is deliberately excluded: the BDTFX itself
# discourages those names, and including them would go against the
# source's editorial signal.
_RETAINED_STATUSES = frozenset({"Recommandé ou typique", "Secondaire ou régional"})


class TelametroAdapter(OwnedClientMixin):
    """Raw TelaMétro client."""

    async def search(self, name: str) -> list[dict]:
        """Return the Algolia hits for a name."""
        params = (
            f"query={name}&hitsPerPage=20&maxValuesPerFacet=10&page=0"
            f"&facetFilters=%5B%22referentiels%3Abdtfx%22%5D&facets=%5B%22referentiels%22%5D&tagFilters="
        )
        payload = {"requests": [{"indexName": "Flore", "params": params}]}
        resp = await self._client.post(ALGOLIA_URL, params=ALGOLIA_PARAMS, json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0].get("hits", []) if results else []

    async def french_common_names(self, name_number: int) -> dict[str, list[str]]:
        """Return the French vernacular names of a record, by status.

        Statuses are "Recommandé ou typique" and "Secondaire ou
        régional" (see `_RETAINED_STATUSES`), in order of appearance,
        deduplicated per status. A missing status has no key. Entirely
        empty if the record has no referenced vernacular name: a normal
        BDTFX state, not an error.
        """
        params = {
            "referentiel": "bdtfx",
            "module": "fiche",
            "num_nom": str(name_number),
            "onglet": "ethnobotanique",
        }
        resp = await self._client.get(ETHNOBOTANY_URL, params=params)
        resp.raise_for_status()

        names: dict[str, list[str]] = {}
        for m in _VERNACULAR_LINE_RE.finditer(resp.text):
            status = m["statut"].strip()
            if m["langue"].strip() != "fra" or status not in _RETAINED_STATUSES:
                continue
            name = html.unescape(m["nom"]).strip()
            if not name:
                continue
            group = names.setdefault(status, [])
            if name not in group:
                group.append(name)
        return names
