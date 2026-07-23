"""Couche d'accès réseau pour The Reptile Database (reptile-database.reptarium.cz) : aucune API
structurée, la fiche espèce est atteinte directement par `/species?genus=X&species=Y` (redirige
vers l'URL canonique `/Genus/species`) sans passer par une page de résultats de recherche
intermédiaire — contrairement à eFloras.org, le site renvoie toujours un HTTP 200, y compris pour
une espèce absente ; seul le contenu du `<h1>` distingue les deux cas."""

from __future__ import annotations

import re

import httpx

BASE_URL = "https://reptile-database.reptarium.cz"

_NOT_FOUND_RE = re.compile(r"<h1>Species <em>[^<]+</em> was not found!</h1>")
_FOUND_RE = re.compile(r"<h1><em>([^<]+)</em>([^<]*)</h1>")


class ReptileDatabaseAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_species(self, genus: str, species: str) -> tuple[str, str | None] | None:
        """Renvoie `(nom_affiché, auteur)` si la fiche existe, `None` sinon. `auteur` est le
        texte brut suivant le nom dans le `<h1>` (ex. "SHAW, 1802" ou "(SHAW, 1802)" — les
        parenthèses signalent un changement de genre depuis la description originale, en
        nomenclature zoologique, mais ne sont pas retirées ici faute de besoin actuel côté
        module), tel quel, non parsé plus finement (année/nom séparés)."""
        resp = await self._client.get(f"{BASE_URL}/species", params={"genus": genus, "species": species})
        resp.raise_for_status()
        if _NOT_FOUND_RE.search(resp.text):
            return None
        match = _FOUND_RE.search(resp.text)
        if not match:
            return None
        nom, auteur = match.groups()
        return nom.strip(), (auteur.strip() or None)
