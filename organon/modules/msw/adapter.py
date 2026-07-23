"""Couche d'accès réseau pour Mammal Species of the World, 3e éd. (MSW3, Bucknell/ASM) :
aucune API structurée, pages `.asp` classiques dont le HTML brut utilise des attributs entre
apostrophes (`href='...'`, `class='...'`) et un `&` littéral (non échappé en `&amp;`) dans les
URL — vérifié en direct sur la réponse serveur, à ne pas confondre avec la sérialisation DOM
d'un navigateur qui, elle, normalise en guillemets doubles et échappe le `&`.

`search.asp?s=<nom>` accepte le paramètre en GET (pas seulement via le formulaire POST du site)
et fait une recherche plein texte sur tous les champs (nom, commentaires, espèce type...) — les
résultats hors nom scientifique portent une annotation `(match on ...)` en dehors du `<span>`,
donc ignorée par construction ; seuls les rangs espèce/sous-espèce sont retenus ici
(`<span class='species|subspecies'>`), la correspondance exacte au nom recherché restant
filtrée par module.py comme pour `organon.modules.eflora`.

L'auteur n'apparaît pas sur la page de résultats, seulement sur la fiche détail
(`browse.asp?s=y&id=...`) : `author()` fait donc un second appel, réservé au seul identifiant
retenu par module.py plutôt qu'à chaque résultat de recherche."""

from __future__ import annotations

import re

import httpx

BASE_URL = "https://www.departments.bucknell.edu/biology/resources/msw3"

_RESULT_RE = re.compile(
    r"browse\.asp\?s=y&id=(\d+)'><span class='(?:species|subspecies)'>([^<]+)</span>"
)
_AUTHOR_RE = re.compile(r"Author:</td>\s*<td[^>]*>([^<]*)</td>", re.IGNORECASE)


class MswAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, name: str) -> list[tuple[int, str]]:
        """Renvoie une liste de `(id, nom_affiché)` pour les résultats de rang espèce ou
        sous-espèce, pas encore filtrée au nom recherché (laissé à module.py). Les noms
        composés sont renvoyés avec une double espace entre genre et épithète côté site
        (ex. `"Panthera  leo"`), normalisée ici."""
        resp = await self._client.get(f"{BASE_URL}/search.asp", params={"s": name})
        resp.raise_for_status()
        return [
            (int(id_s), re.sub(r"\s+", " ", nom).strip())
            for id_s, nom in _RESULT_RE.findall(resp.text)
        ]

    async def author(self, id_: int) -> str | None:
        """Renvoie le champ `Author` de la fiche détail (ex. `"Linnaeus, 1758."`), point final
        retiré, ou `None` si absent."""
        resp = await self._client.get(f"{BASE_URL}/browse.asp", params={"s": "y", "id": id_})
        resp.raise_for_status()
        match = _AUTHOR_RE.search(resp.text)
        if not match:
            return None
        return match.group(1).strip().rstrip(".") or None
