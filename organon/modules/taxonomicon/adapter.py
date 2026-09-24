"""Network access to The Taxonomicon (taxonomicon.taxonomy.nl).

Also known as Systema Naturae 2000. No API was found. The site is a
classic ASP.NET WebForms form whose quick search posts back, then ends
with a GET redirect usable directly:
`TaxonList.aspx?subject=...&by=...&search=...`. The site answers over
HTTP only (no HTTPS).

The general search ("Entity by Scientific Name") mixes taxa with
homonymous non-biological entities (e.g. the minor planet "Quercus"), so
the rank-group searches are used instead
(`subject=Genus/Family/High/Species`), which return only taxa.
Exception: the "below species" group (`subject=Low`) returns nothing for
`by=ScientificName`, even for a trinomial known to the site;
infraspecific taxa are only found through `subject=Entity&by=Epithet` on
the last word, hence the exact full-name filter left to module.py,
indispensable there (the epithet alone also returns taxa of other
genera).
"""

from __future__ import annotations

import asyncio
import re

from organon.core.http import OwnedClientMixin, fetch_text

BASE_URL = "http://taxonomicon.taxonomy.nl"

# Rank groups of the site's scoped search. A one-word name may be a
# genus, a family or a higher rank: the three groups are tried and
# combined, the exact-name filter being left to module.py.
_SUBJECTS_BY_WORD_COUNT: dict[int, tuple[str, ...]] = {
    1: ("Genus", "Family", "High"),
    2: ("Species",),
}

_ROW_RE = re.compile(
    r'<a class="(?P<validity>Valid|Invalid)" href="TaxonTree\.aspx\?id=(?P<id>\d+)&src=\d+">'
    r'<span class="Taxon"><b><i>(?P<nom>[^<]+)</i></b>'
)

_AUTHOR_CITATION_RE = re.compile(
    r'SN2000 author citation</td>.*?<span class="Citation">(?P<auteur>[^<]+)</span>', re.DOTALL
)


class TaxonomiconAdapter(OwnedClientMixin):
    """Raw Taxonomicon client."""

    async def _search(self, subject: str, by: str, term: str) -> list[tuple[str, int, str]]:
        """Return (validity, id, name) rows of one scoped search."""
        resp = await self._client.get(
            f"{BASE_URL}/TaxonList.aspx", params={"subject": subject, "by": by, "search": term}
        )
        resp.raise_for_status()
        return [
            (m.group("validity"), int(m.group("id")), m.group("nom"))
            for m in _ROW_RE.finditer(resp.text)
        ]

    async def search(self, name: str) -> list[tuple[str, int, str]]:
        """Return (validity, id, name) rows of all relevant rank groups.

        Combines the groups fitting the word count of `name`. Not yet
        filtered by exact name or validity (left to module.py, as
        `organon.modules.eflora`).
        """
        words = name.split(" ")
        subjects = _SUBJECTS_BY_WORD_COUNT.get(len(words))
        if subjects is not None:
            results = await asyncio.gather(
                *(self._search(subject, "ScientificName", name) for subject in subjects)
            )
            return [hit for group in results for hit in group]
        return await self._search("Entity", "Epithet", words[-1])

    async def author_citation(self, taxon_id: int) -> str | None:
        """Return the full author citation of a taxon, or None.

        The "SN2000 author citation" (e.g. "(C. Linnaeus, 1758) Pocock,
        1930") from the nomenclature page: search results only give an
        abbreviated one, without the later combination.
        """
        text = await fetch_text(
            self._client, f"{BASE_URL}/TaxonName.aspx", params={"id": taxon_id, "src": 0}
        )
        if text is None:
            return None
        m = _AUTHOR_CITATION_RE.search(text)
        return m.group("auteur").strip() if m else None
