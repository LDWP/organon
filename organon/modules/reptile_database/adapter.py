"""Couche d'accès réseau pour The Reptile Database (reptile-database.reptarium.cz) : aucune API
structurée, la fiche espèce est atteinte directement par `/species?genus=X&species=Y` (redirige
vers l'URL canonique `/Genus/species`) sans passer par une page de résultats de recherche
intermédiaire — contrairement à eFloras.org, le site renvoie toujours un HTTP 200, y compris pour
une espèce absente ; seul le contenu du `<h1>` distingue les deux cas.

La fiche espèce porte aussi un champ « Higher Taxa » (ex. `"Lacertidae, Lacertinae, Sauria,
Lacertoidea, Squamata (lizards)"`) exploité pour la classification — voir `_parse_higher_taxa`
pour le détail de ce qui en est extrait de façon fiable et ce qui est volontairement ignoré."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

BASE_URL = "https://reptile-database.reptarium.cz"

_NOT_FOUND_RE = re.compile(r"<h1>Species <em>[^<]+</em> was not found!</h1>")
_FOUND_RE = re.compile(r"<h1><em>([^<]+)</em>([^<]*)</h1>")
_HIGHER_TAXA_RE = re.compile(r"<tr><td>Higher Taxa</td><td>([^<]*)</td>")

_ORDRES_CONNUS = frozenset({"Squamata", "Testudines", "Crocodylia", "Rhynchocephalia"})
"""Les 4 seuls ordres de reptiles vivants couverts par la base (squamates, tortues,
crocodiliens, rhynchocéphales) : vocabulaire fermé utilisé par `_parse_higher_taxa` pour repérer
l'ordre dans le champ « Higher Taxa », qui ne porte lui-même aucun rang explicite."""


@dataclass(frozen=True)
class SpeciesHit:
    nom: str
    auteur: str | None
    famille: str | None
    ordre: str | None


def _parse_higher_taxa(raw: str) -> tuple[str | None, str | None]:
    """Découpe le champ « Higher Taxa » en (famille, ordre). Exemples réels observés :
    `"Lacertidae, Lacertinae, Sauria, Lacertoidea, Squamata (lizards)"` ou, pour les
    Crocodylia (seulement 3 familles au total, aucun clade intermédiaire listé),
    `"Crocodylidae (Crocodylia, crocodiles)"`.

    Le champ n'indique aucun rang explicite, et l'ordre des clades intermédiaires (sous-famille,
    super-famille, sous-ordre...) varie d'une fiche à l'autre — ex. "Sauria" cité avant ou après
    "Iguania" selon l'espèce — donc seuls deux éléments en sont extraits de façon fiable :
    - la famille, toujours le premier terme de la liste ;
    - l'ordre, repéré par vocabulaire fermé (`_ORDRES_CONNUS`) plutôt que par position : il
      apparaît tantôt en dernier terme avant le nom vernaculaire entre parenthèses (cas
      général), tantôt à l'intérieur même de la parenthèse (cas Crocodylia ci-dessus)."""
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
    famille = tokens[0]
    if len(tokens) > 1:
        candidat_ordre = tokens[-1]
    elif paren:
        candidat_ordre = paren.split(",", 1)[0].strip()
    else:
        candidat_ordre = None
    ordre = candidat_ordre if candidat_ordre in _ORDRES_CONNUS else None
    return famille, ordre


class ReptileDatabaseAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_species(self, genus: str, species: str) -> SpeciesHit | None:
        """Renvoie la fiche si elle existe, `None` sinon. `auteur` est le texte brut suivant le
        nom dans le `<h1>` (ex. "SHAW, 1802" ou "(SHAW, 1802)" — les parenthèses signalent un
        changement de genre depuis la description originale, en nomenclature zoologique, mais
        ne sont pas retirées ici faute de besoin actuel côté module), tel quel, non parsé plus
        finement (année/nom séparés). `famille`/`ordre` sont `None` si le champ « Higher Taxa »
        est absent de la fiche ou si son contenu ne suit pas le format attendu (voir
        `_parse_higher_taxa`)."""
        resp = await self._client.get(
            f"{BASE_URL}/species", params={"genus": genus, "species": species}
        )
        resp.raise_for_status()
        if _NOT_FOUND_RE.search(resp.text):
            return None
        match = _FOUND_RE.search(resp.text)
        if not match:
            return None
        nom, auteur = match.groups()

        famille, ordre = None, None
        higher_taxa_match = _HIGHER_TAXA_RE.search(resp.text)
        if higher_taxa_match:
            famille, ordre = _parse_higher_taxa(higher_taxa_match.group(1))

        return SpeciesHit(
            nom=nom.strip(), auteur=(auteur.strip() or None), famille=famille, ordre=ordre
        )
