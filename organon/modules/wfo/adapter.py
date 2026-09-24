"""Network access to World Flora Online, through its GraphQL API.

The API (`https://list.worldfloraonline.org/gql.php`, open
introspection) feeds wfoplantlist.org; it is not an HTML scraping of
`worldfloraonline.org`. Ids (`wfo-<n>`) are the same on both sites:
external links and citations still point to `worldfloraonline.org` (see
`module.py`), the API only serves search and classification.

`taxonNameSuggestion` is a term autocomplete: `nameString` returns only
the last epithet, and the answer mixes homonyms with unrelated taxa
sharing a term. `fullNameStringNoAuthorsPlain` gives the full name at
any rank and serves as the exact filter, left to `module.py`.

`taxonNameById(id).currentPreferredUsage.path` gives the full chain of
the accepted taxon up to the technical root (rank `code`, not a real
rank; see `organon.modules.wfo.ranks`), with each ancestor's exact rank
(GraphQL `Rank` enum).
"""

from __future__ import annotations

from organon.core.http import OwnedClientMixin

GRAPHQL_URL = "https://list.worldfloraonline.org/gql.php"

_SEARCH_QUERY = """
query($terms: String!, $limit: Int!) {
  taxonNameSuggestion(termsString: $terms, limit: $limit, excludeDeprecated: false) {
    id
    fullNameStringNoAuthorsPlain
    authorsString
    rank
    role
  }
}
"""

_ANCESTORS_QUERY = """
query($id: String!) {
  taxonNameById(nameId: $id) {
    currentPreferredUsage {
      path { hasName { fullNameStringNoAuthorsPlain rank authorsString } }
    }
  }
}
"""

# Wide enough to cover the homonyms of the name despite the autocomplete
# noise of `taxonNameSuggestion`, without paginating.
SEARCH_LIMIT = 50


class WfoAdapter(OwnedClientMixin):
    """Raw WFO GraphQL client."""

    async def _graphql(self, query: str, variables: dict) -> dict | None:
        """Run a GraphQL query; return its data, or None on error."""
        resp = await self._client.post(GRAPHQL_URL, json={"query": query, "variables": variables})
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            return None
        return payload.get("data")

    async def search(self, name: str) -> list[dict]:
        """Return `{id, nom, auteur, statut, rang_brut}` per result.

        Not yet filtered to the searched name (left to module.py).
        """
        data = await self._graphql(_SEARCH_QUERY, {"terms": name, "limit": SEARCH_LIMIT})
        if not data:
            return []
        return [
            {
                "id": r["id"],
                "nom": r["fullNameStringNoAuthorsPlain"],
                "auteur": r.get("authorsString"),
                "statut": r["role"],
                "rang_brut": r.get("rank"),
            }
            for r in data.get("taxonNameSuggestion") or []
        ]

    async def ancestors(self, wfo_id: str) -> list[dict]:
        """Return the ancestors, nearest first.

        Each is `{nom, auteur, rang_brut}`, up to the root node (rank
        `code`), without the taxon itself. `path` already comes in that
        order, its first element being the taxon, excluded here.
        """
        data = await self._graphql(_ANCESTORS_QUERY, {"id": wfo_id})
        if not data or not data.get("taxonNameById"):
            return []
        path = (data["taxonNameById"].get("currentPreferredUsage") or {}).get("path") or []
        return [
            {
                "nom": p["hasName"]["fullNameStringNoAuthorsPlain"],
                "auteur": p["hasName"].get("authorsString"),
                "rang_brut": p["hasName"]["rank"],
            }
            for p in path[1:]
        ]
