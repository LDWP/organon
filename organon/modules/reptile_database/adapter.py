"""Network access to The Reptile Database: no structured API.

The species page is reached directly by `/species?genus=X&species=Y`
(redirecting to `/Genus/species`), with no search result page. The site
always answers HTTP 200, even for an absent species; only the `<h1>`
tells the two apart.

The page also has a "Higher Taxa" field used for the classification; see
`_parse_higher_taxa`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from organon.core.http import OwnedClientMixin

BASE_URL = "https://reptile-database.reptarium.cz"

_NOT_FOUND_RE = re.compile(r"<h1>Species <em>[^<]+</em> was not found!</h1>")
_FOUND_RE = re.compile(r"<h1><em>([^<]+)</em>([^<]*)</h1>")
_HIGHER_TAXA_RE = re.compile(r"<tr><td>Higher Taxa</td><td>([^<]*)</td>")
_SEARCH_RESULTS_RE = re.compile(r"<h1>Search results</h1>")
_SEARCH_NOT_FOUND_RE = re.compile(r"<p>No species were found\.</p>")

# The only 4 orders of living reptiles in the database: closed
# vocabulary used by `_parse_higher_taxa` to spot the order.
_KNOWN_ORDERS = frozenset({"Squamata", "Testudines", "Crocodylia", "Rhynchocephalia"})


@dataclass(frozen=True)
class SpeciesHit:
    """A species page: name, author, family and order."""

    nom: str
    auteur: str | None
    famille: str | None
    ordre: str | None


def _parse_higher_taxa(raw: str) -> tuple[str | None, str | None]:
    """Split the "Higher Taxa" field into (family, order).

    E.g. "Lacertidae, Lacertinae, Sauria, Lacertoidea, Squamata
    (lizards)" or, for Crocodylia, "Crocodylidae (Crocodylia,
    crocodiles)". The field has no explicit rank and the order of the
    intermediate clades varies, so only two items are reliable:
    - the family, always the first term;
    - the order, found by closed vocabulary (`_KNOWN_ORDERS`) rather
      than by position: last term before the parenthesis, or inside it.
    """
    text = raw.strip()
    if not text:
        return None, None
    paren_match = re.search(r"\(([^()]*)\)\s*$", text)
    if paren_match:
        main, paren = text[: paren_match.start()].strip(), paren_match.group(1)
    else:
        main, paren = text, None
    tokens = [t.strip() for t in main.split(",") if t.strip()]
    if not tokens:
        return None, None
    family = tokens[0]
    if len(tokens) > 1:
        order_candidate = tokens[-1]
    elif paren:
        order_candidate = paren.split(",", 1)[0].strip()
    else:
        order_candidate = None
    order = order_candidate if order_candidate in _KNOWN_ORDERS else None
    return family, order


class ReptileDatabaseAdapter(OwnedClientMixin):
    """Raw Reptile Database client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """Use `client` if given, else create one."""
        super().__init__(client, follow_redirects=True)

    async def get_species(self, genus: str, species: str) -> SpeciesHit | None:
        """Return the species page, or None if absent.

        `author` is the raw text after the name in the `<h1>` (e.g.
        "SHAW, 1802"; parentheses mean a genus change), left unparsed.
        Family and order are None if "Higher Taxa" is absent or
        malformed.
        """
        resp = await self._client.get(
            f"{BASE_URL}/species", params={"genus": genus, "species": species}
        )
        resp.raise_for_status()
        if _NOT_FOUND_RE.search(resp.text):
            return None
        match = _FOUND_RE.search(resp.text)
        if not match:
            return None
        name, author = match.groups()

        family, order = None, None
        higher_taxa_match = _HIGHER_TAXA_RE.search(resp.text)
        if higher_taxa_match:
            family, order = _parse_higher_taxa(higher_taxa_match.group(1))

        return SpeciesHit(
            nom=name.strip(), auteur=(author.strip() or None), famille=family, ordre=order
        )

    async def _advanced_search_exists(self, field: str, value: str) -> bool:
        """Return True if the advanced search finds the value.

        The site has no genus or family page, only this search form
        listing the matching species. `exact[]` is needed: without it
        the match is by substring (`genus=Varan` also returns the
        species of *Varanus*).
        """
        # The site redirects the form submission (`ok`/`do`) to this
        # URL; submitting it directly is stable, whereas the form
        # handler sometimes answers the bare form.
        params = {field: value, "exact[0]": field, "submit": "Search"}
        resp = await self._client.get(f"{BASE_URL}/advanced_search", params=params)
        resp.raise_for_status()
        # Anything but a results page (e.g. the bare form) is not a
        # confirmation: a false positive would cite an unrelated taxon.
        return bool(_SEARCH_RESULTS_RE.search(resp.text)) and not _SEARCH_NOT_FOUND_RE.search(
            resp.text
        )

    async def genus_exists(self, genus: str) -> bool:
        """Return True if the genus has species."""
        return await self._advanced_search_exists("genus", genus)

    async def family_exists(self, family: str) -> bool:
        """Return True if the family or order has species.

        "Higher Taxa" mixes family and order; searching uses the same
        `taxon` field.
        """
        return await self._advanced_search_exists("taxon", family)
