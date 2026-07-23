"""Couche d'accès réseau pour The Taxonomicon (taxonomicon.taxonomy.nl, alias Systema Naturae
2000) : aucune API trouvée (sondé en direct). Le site est un formulaire ASP.NET WebForms
classique dont la recherche rapide déclenche un postback, mais celui-ci se termine par une
redirection GET exploitable directement : `TaxonList.aspx?subject=...&by=...&search=...`. Le
site ne répond qu'en HTTP (pas de HTTPS, vérifié en direct).

La recherche générale ("Entity by Scientific Name") mélange taxons et entités non biologiques
homonymes (ex. la planète mineure "Quercus" pour le genre végétal du même nom) : on utilise donc
les recherches scopées par groupe de rang du site (`subject=Genus/Family/High/Species`), qui ne
renvoient que des taxons ("N taxa found" plutôt que "N entities found"). Exception : le groupe
« below species » (`subject=Low`) s'est révélé ne renvoyer aucun résultat en `by=ScientificName`
même pour un trinôme exact connu du site (sondé en direct, ex. « Vulpes vulpes crucigera »,
pourtant bien présent) ; les taxons infraspécifiques n'y sont retrouvables que par
`subject=Entity&by=Epithet` sur le dernier mot du nom, d'où le filtrage par nom complet exact
laissé à module.py qui reste indispensable dans ce cas précis (l'épithète seule remonte aussi des
taxons d'autres genres)."""

from __future__ import annotations

import re

import httpx

BASE_URL = "http://taxonomicon.taxonomy.nl"

# Groupes de rang de la recherche scopée du site. Un nom d'un seul mot peut être un genre, une
# famille ou un rang supérieur (ordre, classe...) : les trois groupes sont essayés et leurs
# résultats combinés, le filtrage par nom exact étant laissé à module.py.
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


class TaxonomiconAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _search(self, subject: str, by: str, term: str) -> list[tuple[str, int, str]]:
        resp = await self._client.get(
            f"{BASE_URL}/TaxonList.aspx", params={"subject": subject, "by": by, "search": term}
        )
        resp.raise_for_status()
        return [
            (m.group("validity"), int(m.group("id")), m.group("nom"))
            for m in _ROW_RE.finditer(resp.text)
        ]

    async def search(self, name: str) -> list[tuple[str, int, str]]:
        """Renvoie une liste de `(validité, id, nom)`, en combinant tous les groupes de rang
        pertinents pour le nombre de mots de `name` — pas encore filtrée par nom exact ni par
        validité (laissé à module.py, comme `organon.modules.eflora`)."""
        words = name.split(" ")
        subjects = _SUBJECTS_BY_WORD_COUNT.get(len(words))
        if subjects is not None:
            hits: list[tuple[str, int, str]] = []
            for subject in subjects:
                hits.extend(await self._search(subject, "ScientificName", name))
            return hits
        return await self._search("Entity", "Epithet", words[-1])

    async def author_citation(self, taxon_id: int) -> str | None:
        """Renvoie la citation d'auteur complète ("SN2000 author citation", ex. "(C. Linnaeus,
        1758) Pocock, 1930") depuis la fiche de nomenclature du taxon — absente des résultats de
        recherche, qui ne donnent qu'une citation abrégée (ex. "(Linnaeus, 1758)" sans le
        renvoi de combinaison ultérieure)."""
        resp = await self._client.get(
            f"{BASE_URL}/TaxonName.aspx", params={"id": taxon_id, "src": 0}
        )
        if resp.status_code >= 400:
            return None
        m = _AUTHOR_CITATION_RE.search(resp.text)
        return m.group("auteur").strip() if m else None
