"""Couche d'accès réseau pour World Flora Online : l'API GraphQL qui alimente wfoplantlist.org
(`https://list.worldfloraonline.org/gql.php`, introspection ouverte, endpoint découvert dans le
bundle JS du site — CORS bloque l'appel direct depuis un navigateur sur cette origine, sans
incidence ici puisque l'appel se fait côté serveur) — pas le scraping HTML de
`worldfloraonline.org` (portail historique, sans schéma exposé, utilisé par la première version
de ce module). Mêmes identifiants `wfo-<n>` des deux côtés (vérifié : Cyperaceae = wfo-7000000170
sur les deux sites) : seuls les liens externes/citations restent pointés vers
`worldfloraonline.org` (voir `module.py`), l'API ne servant qu'à la recherche et à la
classification.

`taxonNameSuggestion` fait de l'auto-complétion par terme : le champ `nameString` d'un résultat
ne renvoie que son dernier épithète (ex. "robur" pour "Quercus robur" — inutilisable pour un
filtre de correspondance exacte), et la réponse mélange les homonymes du nom demandé avec des
taxons non apparentés partageant seulement un terme (vérifié sur "Quercus robur" : les deux
homonymes attendus, mais aussi des variétés sans rapport comme "Quercus robur var. brevipes").
`fullNameStringNoAuthorsPlain` donne le nom complet correct à tout rang (y compris les rangs
infragénériques comme "Quercus sect. Quercus", vérifié en direct) et sert ici de filtre exact,
laissé à `module.py` comme avant.

`taxonNameById(id).currentPreferredUsage.path` donne la chaîne complète et non tronquée du
taxon accepté jusqu'à la racine technique (rang `code`, pas un vrai rang taxonomique — voir
`organon.modules.wfo.ranks`), avec le rang exact de chaque ancêtre (enum GraphQL `Rank`) : plus
besoin de le déduire par terminaison latine comme la première version de ce module."""

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

SEARCH_LIMIT = 50
"""Assez large pour couvrir les homonymes du nom demandé malgré le bruit d'auto-complétion
propre à `taxonNameSuggestion` (voir docstring du module), sans avoir à paginer."""


class WfoAdapter(OwnedClientMixin):
    async def _graphql(self, query: str, variables: dict) -> dict | None:
        resp = await self._client.post(GRAPHQL_URL, json={"query": query, "variables": variables})
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            return None
        return payload.get("data")

    async def search(self, name: str) -> list[dict]:
        """Renvoie une liste de `{id, nom, auteur, statut, rang_brut}` — pas encore filtrée au
        nom recherché (laissé à module.py)."""
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
        """Renvoie la chaîne des ancêtres `{nom, auteur, rang_brut}`, triée du parent le plus
        proche vers le nœud racine (rang technique `code`, voir docstring du module) — sans le
        taxon lui-même. `path` est déjà dans cet ordre côté GraphQL (le taxon lui-même en
        premier élément, exclu ici) : aucun tri à refaire."""
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
